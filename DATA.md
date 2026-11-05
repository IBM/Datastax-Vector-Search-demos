# Synthetic data and fixtures

The collection embeds newly prepared illustrative data in notebook code or generates it at runtime. It contains no customer/prospect records, real personnel data, scraped corpus, downloaded benchmark dataset, foundation-model weights or checkpoints. Some content was prepared with AI assistance; exact historical model provenance is unverified. These statements describe the source collection and do not assert that synthetic fixtures are exempt from IBM's data-review process.

## AI-related examples

| Notebook | Data and intended use |
| --- | --- |
| [Device customization preparation](examples/services/customization_job_workflow.ipynb) | 48 rule-labeled fictional temperature readings, split into 36 training and 12 validation chat pairs; data/job validation only, no default model training. |
| [HTML-to-training QA](examples/services/html_to_training_qa.ipynb) | Four authored HTML policy documents; derived source-traceable QA/chat pairs and document-separated training/validation splits. |
| [Retrieval fusion](examples/science/ensemble-retrieval/tutorial.ipynb) | Nine authored heat-pump/battery/water-pump passages and four queries with relevance judgments; optional embedding/CrossEncoder evaluation. |
| [NVIDIA reranking](examples/science/nvidia-reranking/tutorial.ipynb) | Six authored air-filter/distractor passages and a synthetic query with relevance expectations; optional model-backed reranking. |
| [Knowledge graph](examples/science/knowledge-graph/tutorial.ipynb) | Four fictional documents about invented people, organizations, instruments and missions; optional structured extraction. |
| [Translation](examples/local/translation-workflow/tutorial.ipynb) | Three authored English segments and Spanish fixture translations; optional watsonx.ai translation. |
| [Retrieval evaluation](examples/services/evaluation_experiments.ipynb) | Four fictional policy passages and ten direct/paraphrased/unsupported question cases; local evaluation and optional Phoenix recording. |
| [Adversarial authorization](examples/services/adversarial_agent_evaluation.ipynb) | Three fictional training-hours records and six authored adversarial/control cases; no real personnel or external attack corpus. |
| [Runtime context](examples/services/watsonx_runtime_context.ipynb) | Five fictional leave events and generic tenant/employee identifiers; local authorization tests and optional Orchestrate request. |
| [Tool agent](examples/services/tool_agent_evaluation.ipynb) | Two fictional equipment types, read-only tool contracts and three authored trajectories; optional Claude exchange. |
| [LangGraph](examples/services/langgraph_evaluation.ipynb), [Orchestrate evaluation](examples/services/watsonx_orchestrate_evaluation.ipynb), [workflow agent](examples/services/workflow_agent_evaluation.ipynb) | Authored policy statements, questions, routing/tool traces and expected results; local regression cases, with separately labeled optional services where present. |

## Other fixtures

Local tutorials use six invented contribution/amendment records, two products with four sale/refund lines, four invented coordinate pairs, five authored question pairs, eight invented latency values, three fictional bibliographic records, two short authored chunking documents, offline HTML/XML strings and generated solid-color images. Quantum tutorials generate mathematical state vectors, circuit results and simulation/calibration arrays. Packaging and SDK tests use tiny synthetic files, request/response fixtures and deliberately malformed variants. Record counts describe primary fixtures, not every negative test, derived chunk, resample or simulation array.

The inputs are intentionally small and support no population-level inference, production performance or model-generalization claim. Default paths do not fetch external datasets. A user opting into hosted APIs must review what synthetic inputs are submitted and the provider's terms/costs; replacing these fixtures with real data requires a new privacy, rights and security review.
