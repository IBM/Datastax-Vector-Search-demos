# Copyright IBM Corp. 2026
# SPDX-License-Identifier: Apache-2.0
# Modified for open-source preparation on 2026-10-23.
# AI assistance: may include Anthropic Claude Opus 4+, Sonnet 3.7+, and
# OpenAI GPT-4+ model contributions; exact per-file provenance is unverified.
# See AI_DISCLOSURE.md and NOTICE.md at the collection root.

"""Exercise optional notebook adapters with actual SDKs and synthetic HTTP fixtures.

Install both optional hashed profiles before running. No provider is contacted.
These tests establish local request/response compatibility, not live service behavior.
"""

import ast
import contextlib
import hashlib
import importlib.metadata
import io
import json
import logging
import os
import socket
import tempfile
import traceback
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import h11
import httpx
import httpx2
from phoenix.client.resources import experiments as phoenix_experiments
from release_evidence import (
    OPTIONAL_INPUTS,
    OPTIONAL_NOTEBOOKS,
    OPTIONAL_VERIFIERS,
    hashes,
    verify_installed_lock,
)

ROOT = Path(__file__).resolve().parents[1]


def run_branch(relative, flag, namespace=None, stdout=None):
    """Execute real notebook cells through the selected opt-in branch."""
    namespace = {} if namespace is None else namespace
    notebook = json.loads((ROOT / relative).read_text())
    with contextlib.redirect_stdout(io.StringIO() if stdout is None else stdout):
        for cell in notebook["cells"]:
            if cell["cell_type"] != "code":
                continue
            tree = ast.parse("".join(cell["source"]))
            selected = False
            for node in tree.body:
                if isinstance(node, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id == flag for target in node.targets
                ):
                    if not isinstance(node.value, ast.Constant) or node.value.value is not False:
                        raise AssertionError("Provider flag must default to False")
                    node.value = ast.Constant(value=True)
                    selected = True
            exec(compile(ast.fix_missing_locations(tree), relative, "exec"), namespace)
            if selected:
                return namespace
    raise AssertionError("Expected optional branch was not found")


@contextlib.contextmanager
def fixture_client(module, handler):
    original = module.Client
    clients = []

    class FixtureClient(original):
        def __init__(self, **kwargs):
            if kwargs.get("trust_env") is not False or kwargs.get("follow_redirects") is not False:
                raise AssertionError("Adapter must disable ambient proxies and redirects")
            if kwargs.get("verify", True) is not True or kwargs.get("timeout") is None:
                raise AssertionError("Adapter must verify TLS and set a timeout")
            super().__init__(transport=module.MockTransport(handler), **kwargs)
            clients.append(self)

    with patch.object(module, "Client", FixtureClient):
        yield clients
    if not clients or not all(client.is_closed for client in clients):
        raise AssertionError("Adapter did not close its HTTP clients")


class OptionalContracts(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / ".build/contract-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(temporary.cleanup)
        home = Path(temporary.name)
        # Clear inherited credentials before executing any notebook code.
        self.enterContext(
            patch.dict(
                os.environ,
                {
                    "ANTHROPIC_API_KEY": "synthetic-test-key",
                    "ANTHROPIC_MODEL": "synthetic-model",
                    "ANTHROPIC_BASE_URL": "http://unapproved.invalid",
                    "OPENAI_API_KEY": "synthetic-test-key",
                    "OPENAI_BASE_URL": "http://unapproved.invalid",
                    "OPENAI_EMBEDDING_MODEL": "synthetic-embedding",
                    "OPENAI_EXTRACTION_MODEL": "synthetic-extraction",
                    "HTTPS_PROXY": "http://unapproved.invalid",
                    "MPLBACKEND": "Agg",
                    "MPLCONFIGDIR": str(home / "matplotlib"),
                    "HOME": str(home),
                    "TMPDIR": str(home),
                },
                clear=True,
            )
        )
        for method in ("connect", "connect_ex"):
            self.enterContext(
                patch.object(
                    socket.socket,
                    method,
                    side_effect=AssertionError("Real network forbidden in contract tests"),
                )
            )
        self.enterContext(
            patch.object(
                socket,
                "getaddrinfo",
                side_effect=AssertionError("Real DNS forbidden in contract tests"),
            )
        )

    def test_anthropic_tool_exchange(self):
        requests = []

        def handler(request):
            self.assertEqual(str(request.url), "https://api.anthropic.com/v1/messages")
            self.assertEqual(request.headers["authorization"], "Bearer synthetic-test-key")
            body = json.loads(request.content)
            requests.append(body)
            self.assertEqual(len(body["tools"]), 2)
            if len(requests) == 1:
                content = [
                    {"type": "text", "text": "Checking both policies."},
                    {
                        "type": "tool_use",
                        "id": "t1",
                        "name": "inventory",
                        "input": {"item": "camera"},
                    },
                    {
                        "type": "tool_use",
                        "id": "t2",
                        "name": "loan_policy",
                        "input": {"item": "camera"},
                    },
                ]
                stop = "tool_use"
            else:
                self.assertEqual(len(requests), 2)
                self.assertEqual(
                    body["messages"][1]["content"][0]["text"], "Checking both policies."
                )
                results = body["messages"][-1]["content"]
                self.assertEqual([x["tool_use_id"] for x in results], ["t1", "t2"])
                self.assertEqual(
                    [json.loads(x["content"]) for x in results],
                    [{"available": 3}, {"loan_days": 14}],
                )
                content = [{"type": "text", "text": "Three cameras for fourteen days."}]
                stop = "end_turn"
            return httpx2.Response(
                200,
                json={
                    "id": f"msg_{len(requests)}",
                    "type": "message",
                    "role": "assistant",
                    "model": "synthetic-model",
                    "content": content,
                    "stop_reason": stop,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 20, "output_tokens": 15},
                },
            )

        with fixture_client(httpx2, handler):
            ns = run_branch("examples/services/tool_agent_evaluation.ipynb", "RUN_LIVE")
        self.assertEqual(len(requests), 2)
        self.assertTrue(
            ns["score"](ns["CASES"][2], {"trace": ns["live_trace"], "facts": ns["facts"]})[
                "trajectory_correct"
            ]
        )

    def test_openai_embeddings_and_structured_extraction(self):
        for slug, flag in (
            ("ensemble-retrieval", "RUN_HOSTED_EMBEDDINGS"),
            ("knowledge-graph", "RUN_LLM_EXTRACTION"),
        ):
            with self.subTest(notebook=slug):
                requests = []
                ns = {}

                def handler(request):
                    requests.append(request)
                    self.assertEqual(request.url.host, "api.openai.com")
                    self.assertEqual(request.url.scheme, "https")
                    self.assertEqual(request.headers["authorization"], "Bearer synthetic-test-key")
                    body = json.loads(request.content)
                    if slug == "ensemble-retrieval":
                        self.assertEqual(request.url.path, "/v1/embeddings")
                        return httpx2.Response(
                            200,
                            json={
                                "object": "list",
                                "model": body["model"],
                                "data": [
                                    {
                                        "object": "embedding",
                                        "index": i,
                                        "embedding": [1.0, float(i), 0.5],
                                    }
                                    for i in reversed(range(len(body["input"])))
                                ],
                                "usage": {"prompt_tokens": 10, "total_tokens": 10},
                            },
                        )
                    self.assertEqual(request.url.path, "/v1/responses")
                    self.assertEqual(body["text"]["format"]["type"], "json_schema")
                    self.assertTrue(body["text"]["format"]["strict"])
                    return httpx2.Response(
                        200,
                        json={
                            "id": "resp_fixture",
                            "object": "response",
                            "created_at": 1,
                            "status": "completed",
                            "model": body["model"],
                            "output": [
                                {
                                    "id": "msg_fixture",
                                    "type": "message",
                                    "role": "assistant",
                                    "status": "completed",
                                    "content": [
                                        {
                                            "type": "output_text",
                                            "annotations": [],
                                            "text": json.dumps({"facts": [ns["facts"][0]]}),
                                        }
                                    ],
                                }
                            ],
                        },
                    )

                with fixture_client(httpx2, handler):
                    run_branch(f"examples/science/{slug}/tutorial.ipynb", flag, ns)
                self.assertEqual(len(requests), 1)
                if slug == "ensemble-retrieval":
                    self.assertEqual(ns["vectors"].shape, (len(ns["records"]) + 1, 3))
                else:
                    self.assertEqual(len(ns["checked"]), 1)
                    self.assertEqual(ns["result"].output_parsed.facts[0].subject, "Mira Vale")

    def test_openai_rejects_misaligned_embedding_indices(self):
        for invalid in ("duplicate", "missing", "out_of_range"):
            with self.subTest(response=invalid):
                requests = []

                def handler(request):
                    requests.append(request)
                    body = json.loads(request.content)
                    count = len(body["input"])
                    indices = list(range(count))
                    if invalid == "duplicate":
                        indices[1] = indices[0]
                    elif invalid == "missing":
                        indices.pop()
                    else:
                        indices[-1] = count
                    return httpx2.Response(
                        200,
                        json={
                            "object": "list",
                            "model": body["model"],
                            "data": [
                                {
                                    "object": "embedding",
                                    "index": i,
                                    "embedding": [1.0, float(i), 0.5],
                                }
                                for i in indices
                            ],
                            "usage": {"prompt_tokens": 10, "total_tokens": 10},
                        },
                    )

                with fixture_client(httpx2, handler):
                    with self.assertRaises(ValueError):
                        run_branch(
                            "examples/science/ensemble-retrieval/tutorial.ipynb",
                            "RUN_HOSTED_EMBEDDINGS",
                        )
                self.assertEqual(len(requests), 1)

    def test_sdk_errors_withhold_provider_bodies_and_credentials(self):
        scenarios = [
            (
                "examples/services/tool_agent_evaluation.ipynb",
                "RUN_LIVE",
                "http401",
                "Anthropic request failed with HTTP 401",
            ),
            (
                "examples/science/ensemble-retrieval/tutorial.ipynb",
                "RUN_HOSTED_EMBEDDINGS",
                "http401",
                "OpenAI embedding request failed with HTTP 401",
            ),
            (
                "examples/science/knowledge-graph/tutorial.ipynb",
                "RUN_LLM_EXTRACTION",
                "http401",
                "OpenAI extraction request or response parsing failed with HTTP 401",
            ),
            (
                "examples/science/knowledge-graph/tutorial.ipynb",
                "RUN_LLM_EXTRACTION",
                "invalid_structured_response",
                "OpenAI extraction request or response parsing failed; provider diagnostics were withheld",
            ),
        ]
        for path, flag, scenario, expected_error in scenarios:
            with self.subTest(notebook=path, scenario=scenario):
                requests = []

                def handler(request):
                    requests.append(request)
                    if scenario == "http401":
                        return httpx2.Response(
                            401,
                            json={
                                "type": "error",
                                "error": {
                                    "type": "authentication_error",
                                    "message": "SENSITIVE_RESPONSE_SENTINEL synthetic-test-key",
                                },
                            },
                        )
                    return httpx2.Response(
                        200,
                        json={
                            "id": "resp_fixture",
                            "object": "response",
                            "created_at": 1,
                            "status": "completed",
                            "model": "synthetic-extraction",
                            "output": [
                                {
                                    "id": "msg_fixture",
                                    "type": "message",
                                    "role": "assistant",
                                    "status": "completed",
                                    "content": [
                                        {
                                            "type": "output_text",
                                            "annotations": [],
                                            "text": json.dumps(
                                                {
                                                    "facts": "SENSITIVE_RESPONSE_SENTINEL synthetic-test-key"
                                                }
                                            ),
                                        }
                                    ],
                                }
                            ],
                        },
                    )

                with (
                    contextlib.redirect_stderr(io.StringIO()) as diagnostics,
                    io.StringIO() as output,
                ):
                    with fixture_client(httpx2, handler):
                        try:
                            run_branch(path, flag, stdout=output)
                        except RuntimeError as exc:
                            self.assertEqual(str(exc), expected_error)
                            self.assertTrue(exc.__suppress_context__)
                            rendered_error = "".join(traceback.format_exception(exc))
                        else:
                            self.fail("SDK HTTP/parsing failure unexpectedly passed")
                    for text in (output.getvalue(), diagnostics.getvalue(), rendered_error):
                        self.assertNotIn("SENSITIVE_RESPONSE_SENTINEL", text)
                        self.assertNotIn("synthetic-test-key", text)
                self.assertEqual(len(requests), 1)

    def test_phoenix_sdk_persistence_and_sanitized_failures(self):
        for scenario in (
            "success",
            "evaluation_storage_503",
            "missing_task",
            "missing_evaluation",
            "wrong_dataset",
            "wrong_metadata",
            "altered_task_output",
            "altered_evaluation_score",
            "altered_evaluation_error",
        ):
            with self.subTest(scenario=scenario):
                os.environ.update(
                    {
                        "PHOENIX_COLLECTOR_ENDPOINT": "https://phoenix.example",
                        "PHOENIX_API_KEY": "synthetic-test-key",
                        "PHOENIX_DATASET": "synthetic-cases",
                        "OTEL_SDK_DISABLED": "false",
                    }
                )
                namespace, requests, persisted_tasks, persisted_evaluations = {}, [], [], []
                previous_logging = logging.root.manager.disable

                def handler(request):
                    self.assertEqual(request.url.scheme, "https")
                    self.assertEqual(request.url.host, "phoenix.example")
                    self.assertEqual(request.headers["authorization"], "Bearer synthetic-test-key")
                    requests.append((request.method, request.url.path))
                    examples = [
                        {
                            "id": f"example-{i}",
                            "node_id": f"example-{i}",
                            "input": {"question": question},
                            "output": {"fact": fact, "source": source},
                            "metadata": {},
                            "updated_at": "2026-10-03T00:00:00Z",
                        }
                        for i, (question, fact, source, _) in enumerate(namespace["CASES"])
                    ]
                    if scenario == "wrong_dataset":
                        examples[0]["output"] = {"fact": "UNAPPROVED_RESPONSE_SENTINEL"}
                    if scenario == "wrong_metadata":
                        examples[0]["metadata"] = {"private": "UNAPPROVED_RESPONSE_SENTINEL"}
                    experiment = {
                        "id": "experiment-1",
                        "dataset_id": "dataset-1",
                        "dataset_version_id": "version-1",
                        "name": "synthetic-evidence-abstention",
                        "description": None,
                        "repetitions": 1,
                        "metadata": {},
                        "project_name": "synthetic",
                    }
                    path = request.url.path
                    if path == "/v1/datasets":
                        self.assertEqual(request.url.params["name"], "synthetic-cases")
                        body = {"data": [{"id": "dataset-1", "name": "synthetic-cases"}]}
                    elif path == "/v1/datasets/dataset-1":
                        body = {"data": {"id": "dataset-1", "name": "synthetic-cases"}}
                    elif path == "/v1/datasets/dataset-1/examples":
                        body = {"data": {"version_id": "version-1", "examples": examples}}
                    elif path == "/v1/datasets/dataset-1/experiments":
                        self.assertEqual(json.loads(request.content)["repetitions"], 1)
                        body = {"data": experiment}
                    elif path == "/v1/experiments/experiment-1/runs":
                        if request.method == "POST":
                            row = json.loads(request.content)
                            row["id"] = f"run-{len(persisted_tasks)}"
                            persisted_tasks.append(row)
                            body = {"data": {"id": row["id"]}}
                        else:
                            task_rows = (
                                persisted_tasks[:-1]
                                if scenario == "missing_task"
                                else persisted_tasks
                            )
                            if scenario == "altered_task_output":
                                task_rows = json.loads(json.dumps(task_rows))
                                task_rows[0]["output"]["answer"] = (
                                    "Not true: " + task_rows[0]["output"]["answer"]
                                )
                            body = {"data": task_rows, "next_cursor": None}
                    elif path == "/v1/experiments/experiment-1":
                        body = {"data": experiment}
                    elif path == "/v1/experiments/experiment-1/json":
                        body = []
                        for run in persisted_tasks:
                            annotations = [
                                {
                                    **evaluation["result"],
                                    **{
                                        key: evaluation[key]
                                        for key in (
                                            "name",
                                            "annotator_kind",
                                            "start_time",
                                            "end_time",
                                            "error",
                                        )
                                    },
                                }
                                for evaluation in persisted_evaluations
                                if evaluation["experiment_run_id"] == run["id"]
                            ]
                            if scenario == "missing_evaluation" and run is persisted_tasks[-1]:
                                annotations = []
                            if scenario == "altered_evaluation_score" and annotations:
                                annotations[0]["score"] = 0.0
                            if scenario == "altered_evaluation_error" and annotations:
                                annotations[0]["error"] = "UNAPPROVED_RESPONSE_SENTINEL"
                            body.append(
                                {
                                    "example_id": run["dataset_example_id"],
                                    "repetition_number": 1,
                                    "annotations": annotations,
                                }
                            )
                    elif path == "/v1/experiment_evaluations":
                        row = json.loads(request.content)
                        if scenario == "evaluation_storage_503":
                            return httpx.Response(
                                503, json={"error": "SENSITIVE_RESPONSE_SENTINEL"}
                            )
                        row["id"] = f"evaluation-{len(persisted_evaluations)}"
                        persisted_evaluations.append(row)
                        body = {"data": {"id": row["id"]}}
                    else:
                        raise AssertionError("Unexpected Phoenix SDK request")
                    return httpx.Response(200, json=body)

                with (
                    contextlib.redirect_stderr(io.StringIO()) as diagnostics,
                    io.StringIO() as output,
                ):
                    with patch.object(
                        phoenix_experiments.OTLPSpanExporter,
                        "export",
                        side_effect=AssertionError("Trace export must stay disabled"),
                    ) as trace_export:
                        with fixture_client(httpx, handler):
                            if scenario == "success":
                                run_branch(
                                    "examples/services/evaluation_experiments.ipynb",
                                    "RUN_LIVE",
                                    namespace,
                                    stdout=output,
                                )
                                self.assertEqual(
                                    namespace["recorded"],
                                    {"task_runs": 10, "persisted_evaluations": 10},
                                )
                                self.assertEqual(len(persisted_evaluations), 10)
                            else:
                                with self.assertRaises(RuntimeError) as caught:
                                    run_branch(
                                        "examples/services/evaluation_experiments.ipynb",
                                        "RUN_LIVE",
                                        namespace,
                                        stdout=output,
                                    )
                                self.assertEqual(
                                    str(caught.exception),
                                    "Phoenix experiment failed; no complete persisted result was verified",
                                )
                        trace_export.assert_not_called()
                    for stream in (diagnostics.getvalue(), output.getvalue()):
                        for sensitive in (
                            "SENSITIVE_RESPONSE_SENTINEL",
                            "UNAPPROVED_RESPONSE_SENTINEL",
                            "synthetic-test-key",
                        ):
                            self.assertNotIn(sensitive, stream)
                self.assertEqual(os.environ["OTEL_SDK_DISABLED"], "false")
                self.assertEqual(logging.root.manager.disable, previous_logging)
                if scenario in {"wrong_dataset", "wrong_metadata"}:
                    self.assertTrue(all(method == "GET" for method, _ in requests))

    def test_phoenix_rejects_malformed_endpoints_before_client_creation(self):
        for endpoint in (
            "https:///missing-host",
            "http://phoenix.example",
            "https://phoenix.example?token=synthetic",
            "https://phoenix.example#fragment",
            "https://user:synthetic@example.invalid",
            "https://PRIVATE_TOKEN_PREFIX@example.invalid\uff0fPRIVATE_TOKEN_SUFFIX",
        ):
            with self.subTest(endpoint=endpoint):
                os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = endpoint
                with (
                    patch.object(httpx, "Client", side_effect=AssertionError("No client expected")),
                    contextlib.redirect_stderr(io.StringIO()) as diagnostics,
                    io.StringIO() as output,
                ):
                    try:
                        run_branch(
                            "examples/services/evaluation_experiments.ipynb",
                            "RUN_LIVE",
                            stdout=output,
                        )
                    except ValueError as exc:
                        self.assertEqual(
                            str(exc),
                            "Use an HTTPS Phoenix endpoint without embedded credentials",
                        )
                        rendered_error = "".join(traceback.format_exception(exc))
                    else:
                        self.fail("Malformed Phoenix endpoint unexpectedly succeeded")
                    for rendered in (
                        output.getvalue(),
                        diagnostics.getvalue(),
                        rendered_error,
                    ):
                        for sensitive in ("PRIVATE_TOKEN_PREFIX", "PRIVATE_TOKEN_SUFFIX"):
                            self.assertNotIn(sensitive, rendered)

    def test_service_http_success_and_failure(self):
        cases = [
            (
                "watsonx_orchestrate_evaluation",
                "WXO_CHAT_URL",
                "WXO_BEARER_TOKEN",
                {"choices": [{"message": {"content": "14 days"}}]},
                "messages",
            ),
            (
                "watsonx_runtime_context",
                "WXO_RUNS_URL",
                "WXO_BEARER_TOKEN",
                {k: "synthetic-" + k for k in ("run_id", "thread_id", "task_id", "message_id")},
                "context_variables",
            ),
            (
                "workflow_agent_evaluation",
                "LANGFLOW_RUN_URL",
                "LANGFLOW_API_KEY",
                {"outputs": [{"outputs": [{"results": {"message": {"text": "14 days"}}}]}]},
                "session_id",
            ),
        ]
        for name, endpoint_var, credential_var, payload, field in cases:
            for status in (200, 302, 401, 503):
                with self.subTest(notebook=name, status=status):
                    requests = []
                    os.environ.update(
                        {
                            endpoint_var: "https://service.example/api",
                            credential_var: "synthetic-test-key",
                            "WXO_AGENT_ID": "synthetic-agent",
                        }
                    )

                    def handler(request):
                        requests.append(request)
                        self.assertEqual(str(request.url), "https://service.example/api")
                        self.assertIn(field, json.loads(request.content))
                        return httpx.Response(
                            status,
                            json=payload
                            if status == 200
                            else {"error": "SENSITIVE_RESPONSE_SENTINEL"},
                            headers={"location": "https://unapproved.invalid"},
                        )

                    with fixture_client(httpx, handler):
                        if status == 200:
                            run_branch(f"examples/services/{name}.ipynb", "RUN_LIVE")
                        else:
                            with self.assertRaises(RuntimeError) as caught:
                                run_branch(f"examples/services/{name}.ipynb", "RUN_LIVE")
                            self.assertEqual(
                                str(caught.exception), f"Service request failed with HTTP {status}"
                            )
                    self.assertEqual(len(requests), 1)
            for invalid in (
                "https:///missing-host",
                "http://service.example/api",
                "https://service.example/api?token=synthetic",
                "https://service.example/api#fragment",
            ):
                with self.subTest(notebook=name, endpoint=invalid):
                    os.environ[endpoint_var] = invalid
                    with patch.object(
                        httpx, "Client", side_effect=AssertionError("No client expected")
                    ):
                        with self.assertRaises(ValueError):
                            run_branch(f"examples/services/{name}.ipynb", "RUN_LIVE")

    def test_service_protocol_errors_withhold_malformed_credentials(self):
        adapters = (
            ("watsonx_orchestrate_evaluation", "WXO_CHAT_URL", "WXO_BEARER_TOKEN"),
            ("watsonx_runtime_context", "WXO_RUNS_URL", "WXO_BEARER_TOKEN"),
            ("workflow_agent_evaluation", "LANGFLOW_RUN_URL", "LANGFLOW_API_KEY"),
        )
        credentials = (
            ("newline_header", "PRIVATE_TOKEN_PREFIX\nPRIVATE_TOKEN_SUFFIX"),
            ("unicode_header", "PRIVATE_TOKEN_PREFIX\u2603PRIVATE_TOKEN_SUFFIX"),
        )
        for name, endpoint_var, credential_var in adapters:
            for scenario, credential in credentials:
                with self.subTest(notebook=name, scenario=scenario):
                    os.environ.update(
                        {
                            endpoint_var: "https://service.example/api",
                            credential_var: credential,
                            "WXO_AGENT_ID": "synthetic-agent",
                        }
                    )
                    requests, rejected_headers = [], []

                    def handler(request):
                        requests.append(request)
                        try:
                            # MockTransport omits the wire protocol validation performed
                            # by HTTP Core. Exercise its actual h11 validator, then expose
                            # the HTTPX exception used by the real transport boundary.
                            h11.Request(
                                method=request.method.encode("ascii"),
                                target=request.url.raw_path,
                                headers=request.headers.raw,
                            )
                        except h11.LocalProtocolError as exc:
                            rejected_headers.append(str(exc))
                            raise httpx.LocalProtocolError(str(exc), request=request) from exc
                        self.fail("Malformed credential unexpectedly passed h11 validation")

                    with (
                        contextlib.redirect_stderr(io.StringIO()) as diagnostics,
                        io.StringIO() as output,
                    ):
                        with fixture_client(httpx, handler):
                            try:
                                run_branch(
                                    f"examples/services/{name}.ipynb",
                                    "RUN_LIVE",
                                    stdout=output,
                                )
                            except RuntimeError as exc:
                                self.assertEqual(
                                    str(exc),
                                    "Service transport failed; no response was verified",
                                )
                                self.assertTrue(exc.__suppress_context__)
                                rendered_error = "".join(traceback.format_exception(exc))
                            else:
                                self.fail("Malformed credential unexpectedly succeeded")
                        for rendered in (
                            output.getvalue(),
                            diagnostics.getvalue(),
                            rendered_error,
                        ):
                            # Check both complete and component values: escaped newline
                            # or Unicode representations must not hide a disclosure.
                            for sensitive in (
                                credential,
                                "PRIVATE_TOKEN_PREFIX",
                                "PRIVATE_TOKEN_SUFFIX",
                            ):
                                self.assertNotIn(sensitive, rendered)
                    if scenario == "newline_header":
                        self.assertEqual(len(requests), 1)
                        self.assertEqual(len(rejected_headers), 1)
                        self.assertIn("PRIVATE_TOKEN_PREFIX", rejected_headers[0])
                        self.assertIn("PRIVATE_TOKEN_SUFFIX", rejected_headers[0])
                    else:
                        # HTTPX rejects non-ASCII header text before transport dispatch.
                        self.assertEqual(len(requests), 0)
                        self.assertEqual(len(rejected_headers), 0)


def main():
    report_path = ROOT / "reports/optional-contracts.json"
    report_path.unlink(missing_ok=True)
    for lock in OPTIONAL_INPUTS:
        verify_installed_lock(ROOT, lock)
    input_hashes = hashes(ROOT, OPTIONAL_INPUTS)
    verifier_hashes = hashes(ROOT, OPTIONAL_VERIFIERS)
    source_hashes = hashes(ROOT, OPTIONAL_NOTEBOOKS)
    script_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(OptionalContracts)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1
    paths = OPTIONAL_NOTEBOOKS
    if input_hashes != hashes(ROOT, OPTIONAL_INPUTS) or verifier_hashes != hashes(
        ROOT, OPTIONAL_VERIFIERS
    ):
        raise RuntimeError("Optional dependencies or verifier sources changed during testing")
    if (
        source_hashes != hashes(ROOT, OPTIONAL_NOTEBOOKS)
        or script_hash != hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    ):
        raise RuntimeError("Optional notebook or test script changed during testing")
    report = {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "command": "python _tools/test_optional_contracts.py",
        "status": "passed",
        "input_sha256": input_hashes,
        "verifier_sha256": verifier_hashes,
        "test_methods": result.testsRun,
        "notebooks": len(paths),
        "coverage": "Actual notebook branches with synthetic HTTP responses: SDK serialization, "
        "reordered/malformed embedding indices, SDK HTTP/parsing diagnostic redaction, complete Phoenix SDK persistence/read-back integrity without trace export and with failure redaction, "
        "12 service status scenarios, 12 malformed endpoint cases, and six actual h11/Unicode "
        "header failures with credential-safe diagnostics. "
        "Socket connect/connect_ex/DNS denied. Live providers remain unverified.",
        "packages": {
            p: importlib.metadata.version(p)
            for p in ["anthropic", "openai", "httpx", "httpx2", "arize-phoenix-client"]
        },
        "source_sha256": source_hashes,
        "test_script_sha256": script_hash,
    }
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
