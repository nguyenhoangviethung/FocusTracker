# FocusFlow UML diagrams

This directory contains the as-built diagrams for the thesis. Mermaid sources
are the editable source of truth; generated assets are written to `rendered/`.

| File | Purpose | Thesis placement |
| --- | --- | --- |
| `01_use_case.mmd` | Actors and product capabilities | Requirements analysis |
| `02_component.mmd` | Software components and dependency boundaries | Application architecture |
| `03_deployment.mmd` | Edge-to-cloud runtime topology | Deployment design |
| `04_inference_sequence.mmd` | One realtime inference round trip | Detailed design |
| `05_session_state.mmd` | Desktop session lifecycle | Behavioral design |
| `06_domain_model.mmd` | Core contracts and persisted entities | Data design |

Render all diagrams as SVG and Overleaf-compatible PNG from the repository root:

```bash
bash scripts/render_uml.sh
```

Use relative paths when including the PDFs in LaTeX, for example:

```tex
\includegraphics[width=\textwidth]{../../FocusTracker/docs/uml/rendered/02_component.png}
```

The relative path above is illustrative. When uploading to Overleaf, preserve
the `docs/uml/rendered` directory beneath the thesis project and adjust only the
prefix from the `.tex` file to that directory.
