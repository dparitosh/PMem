# Semantic Bridge, Change Impact, and Teamcenter Integration

This note explains how the UI runs the **change impact** flow, what message to send to the API, and how a Teamcenter action handler can call the same service.

## 1) What the UI is doing

The app has two relevant surfaces:

- **Recommendations tab**: use the **Change Impact** service when you want a structured impact analysis.
- **Graph Explorer tooltip**: the `Impact` button can launch the same change impact service for the selected node.

The change impact flow is meant for:

- part changes
- assembly changes
- requirement changes
- property or attribute changes

It is not the generic chat path. For release use, treat it as a dedicated API.

## 2) Recommended API to call

Use this endpoint:

```http
POST /recommendations/change-impact
```

## 3) Message / payload to pass

The backend accepts either `change_name` or `part_name`. It also accepts an optional `scope` object so the service can stay aligned to the active ontology or graph context.

### Minimal payload

```json
{
  "change_name": "ROTOR SHAFT tolerance change"
}
```

or

```json
{
  "part_name": "ROTOR SHAFT"
}
```

### Recommended payload with scope

```json
{
  "change_name": "ROTOR SHAFT tolerance change",
  "node_id": "12345",
  "scope": {
    "prefix": "plmxml",
    "ontology_id": "mbseout",
    "node_id": "12345"
  }
}
```

### If Teamcenter already knows the selected object

```json
{
  "part_name": "0003257",
  "node_id": "tc-item-0003257",
  "scope": {
    "prefix": "plmxml",
    "ontology_id": "plmxml_xsd_individual",
    "node_id": "tc-item-0003257"
  }
}
```

## 4) Expected response

The response is a structured impact analysis. Key fields include:

- `change_entity`
- `impacted_parts`
- `assembly_impact`
- `impacted_requirements`
- `process_impacts`
- `realization_chain`
- `impact_score`

The UI uses these sections to render the impact summary and detail tables.

## 5) How Teamcenter should call it

For a Teamcenter action handler, send the selected object name or ID to the change impact endpoint.

### Suggested Teamcenter message

```json
{
  "event": "change_impact_analysis",
  "object_type": "ItemRevision",
  "object_name": "0003257",
  "object_id": "12345",
  "ontology_prefix": "plmxml",
  "ontology_id": "plmxml_xsd_individual"
}
```

Then map that into the API payload:

```json
{
  "part_name": "0003257",
  "node_id": "12345",
  "scope": {
    "prefix": "plmxml",
    "ontology_id": "plmxml_xsd_individual",
    "node_id": "12345"
  }
}
```

## 6) How the chat API can be used by Teamcenter

The chat API is a separate path for natural-language assistance. It is useful when Teamcenter wants an assistant-style answer rather than a structured recommendation.

### Chat endpoint

```http
POST /chat
```

### Chat request body

```json
{
  "session_id": "tc-session-001",
  "message": "Explain the traceability impact of changing ROTOR SHAFT tolerance.",
  "graph_context": {
    "view_mode": "context",
    "ontology": "plmxml",
    "selected": {
      "node_id": "12345",
      "label": "ROTOR SHAFT"
    },
    "visible_nodes": 12,
    "visible_links": 11,
    "search_query": "ROTOR SHAFT"
  }
}
```

### When to use chat vs change impact

- Use **`/recommendations/change-impact`** when you need a deterministic impact report.
- Use **`/chat`** when you need conversational guidance, traceability help, or explanation.

## 7) UI behavior to expect

- The **Change Impact** panel should show the selected part or change item.
- The result should include impacted parts, requirements, and process chain.
- The **Graph Explorer** tooltip `Impact` action should reuse the same backend flow.
- The chat assistant should receive the current graph context when launched from the UI.

## 8) Practical release guidance

For customer integration, the safest pattern is:

1. Teamcenter detects the selected object.
2. Teamcenter sends the object name, object ID, and ontology scope.
3. The app calls `/recommendations/change-impact`.
4. The UI renders the structured result.
5. Use `/chat` only for free-form assistant interaction.

## 9) Notes

- The backend accepts `change_name` or `part_name`.
- If you provide `node_id`, the service uses it to narrow the lookup inside the active scope.
- If no `scope` is provided, the service falls back to the default configured graph context.

