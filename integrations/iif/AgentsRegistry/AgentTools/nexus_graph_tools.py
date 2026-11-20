"""Thin IIF FunctionTool adapter; computation stays in the Graph microservice."""
from llama_index.core.tools import FunctionTool
from AgentsRegistry.CodedTools.nexus_graph import compute_selected_graph
nexus_graph_tool = FunctionTool.from_defaults(fn=compute_selected_graph, name='compute_selected_nexus_graph')
