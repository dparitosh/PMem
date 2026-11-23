"""Thin IIF FunctionTool adapter; computation stays in the Graph microservice."""
from llama_index.core.tools import FunctionTool
from AgentsRegistry.CodedTools.eif_dt_graph import eif_dt_compute_selected_graph
eif_dt_graph_tool = FunctionTool.from_defaults(fn=eif_dt_compute_selected_graph, name='eif_dt_compute_selected_graph')
