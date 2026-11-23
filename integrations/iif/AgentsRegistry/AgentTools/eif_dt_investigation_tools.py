"""IIF wrapper for the scoped NEXUS investigation read."""
from llama_index.core.tools import FunctionTool
from AgentsRegistry.CodedTools.eif_dt_investigation import eif_dt_read_selected_investigation

eif_dt_investigation_tool = FunctionTool.from_defaults(fn=eif_dt_read_selected_investigation)
