from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import Field, model_validator

from .models import (
    AddElementOperation,
    AddLayerOperation,
    AddSystemOperation,
    AgentPlan,
    ClearDocumentOperation,
    ConnectorElement,
    DeleteLayerOperation,
    DeleteSystemOperation,
    Point,
    ProviderConfig,
    StrictModel,
    TransactionRequest,
    UpdateElementOperation,
    UpdateLayerOperation,
    UpdateSystemOperation,
)


class SafeDeleteElementOperation(StrictModel):
    op: Literal["delete_element"] = "delete_element"
    element_id: str
    connection_policy: Literal["reject_if_connected", "detach", "delete_connectors"] = (
        "reject_if_connected"
    )


class ReplaceSymbolOperation(StrictModel):
    op: Literal["replace_symbol"] = "replace_symbol"
    element_id: str
    symbol_key: str
    port_mapping: dict[str, str] = Field(default_factory=dict)
    preserve_size: bool = True
    label: str | None = None
    properties_patch: dict[str, Any] = Field(default_factory=dict)


class ReconnectConnectorOperation(StrictModel):
    op: Literal["reconnect_connector"] = "reconnect_connector"
    connector_id: str
    endpoint: Literal["source", "target"]
    element_id: str | None = None
    port_id: str | None = None
    point: Point | None = None
    routing: Literal["orthogonal", "direct", "manual"] | None = None

    @model_validator(mode="after")
    def validate_connection(self) -> ReconnectConnectorOperation:
        bound = self.element_id is not None or self.port_id is not None
        if bound and (self.element_id is None or self.port_id is None):
            raise ValueError("element_id and port_id must be provided together")
        if not bound and self.point is None:
            raise ValueError("a free connector endpoint requires point")
        return self


class ConnectPortsOperation(StrictModel):
    op: Literal["connect_ports"] = "connect_ports"
    connector_id: str = Field(default_factory=lambda: f"el_{uuid4().hex[:12]}")
    source_element_id: str
    source_port_id: str
    target_element_id: str
    target_port_id: str
    routing: Literal["orthogonal", "direct"] = "orthogonal"
    process_tag: str = ""
    medium: str = ""
    nominal_diameter: str = ""
    layer_id: str | None = None
    system_id: str | None = None
    style: dict[str, Any] | None = None
    name: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


SemanticOperation = Annotated[
    AddElementOperation
    | UpdateElementOperation
    | SafeDeleteElementOperation
    | ReplaceSymbolOperation
    | ReconnectConnectorOperation
    | ConnectPortsOperation
    | AddLayerOperation
    | UpdateLayerOperation
    | DeleteLayerOperation
    | AddSystemOperation
    | UpdateSystemOperation
    | DeleteSystemOperation
    | ClearDocumentOperation,
    Field(discriminator="op"),
]


class SemanticTransaction(StrictModel):
    operations: list[SemanticOperation] = Field(min_length=1, max_length=500)
    expected_revision: int | None = Field(default=None, ge=0)
    label: str = ""


class SemanticAgentPlan(StrictModel):
    plan_id: str = Field(default_factory=lambda: uuid4().hex)
    explanation: str = ""
    transaction: SemanticTransaction


class AgentOperationIssue(StrictModel):
    operation_index: int | None = Field(default=None, ge=0)
    operation: str = ""
    code: str
    message: str
    field_path: str = ""
    element_id: str | None = None
    connector_id: str | None = None
    available_values: dict[str, list[str]] = Field(default_factory=dict)
    suggestions: list[str] = Field(default_factory=list)


class AgentTransactionAssessment(StrictModel):
    valid: bool
    stage: Literal["compile", "validate"]
    document_id: str
    current_revision: int = Field(ge=0)
    next_revision: int = Field(ge=0)
    semantic_operation_count: int = Field(default=0, ge=0)
    compiled_operation_count: int = Field(default=0, ge=0)
    resulting_element_count: int | None = Field(default=None, ge=0)
    affected_element_ids: list[str] = Field(default_factory=list)
    added_element_ids: list[str] = Field(default_factory=list)
    updated_element_ids: list[str] = Field(default_factory=list)
    deleted_element_ids: list[str] = Field(default_factory=list)
    issues: list[AgentOperationIssue] = Field(default_factory=list)


class SemanticAgentPlanResult(StrictModel):
    plan: SemanticAgentPlan
    compiled_plan: AgentPlan | None = None
    assessment: AgentTransactionAssessment
    attempt: int = Field(default=0, ge=0, le=5)
    parent_plan_id: str | None = None


class SemanticAgentReplanRequest(StrictModel):
    prompt: str = Field(min_length=1, max_length=100_000)
    context: str = Field(default="", max_length=200_000)
    provider: ProviderConfig | None = None
    expected_revision: int | None = Field(default=None, ge=0)
    failed_plan: SemanticAgentPlan
    attempt: int = Field(default=1, ge=1, le=5)


class CompiledSemanticTransaction(StrictModel):
    transaction: TransactionRequest | None = None
    assessment: AgentTransactionAssessment


class SemanticConnectorPreview(StrictModel):
    connector: ConnectorElement
