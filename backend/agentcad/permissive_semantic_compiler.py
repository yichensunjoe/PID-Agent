from __future__ import annotations

from .agent_semantic_models import CompiledSemanticTransaction, SemanticOperation, SemanticTransaction
from .semantic_compiler_engine import SemanticTransactionCompiler as StrictSemanticTransactionCompiler


class PermissiveSemanticTransactionCompiler(StrictSemanticTransactionCompiler):
    """Compile as much of a model plan as can be applied safely.

    A single malformed or unsupported drawing operation should not discard an
    otherwise useful P&ID. The strict compiler remains authoritative for every
    operation that is retained; invalid operations are skipped individually.
    Revision conflicts are never bypassed, and no low-level transaction is
    returned unless it passes the normal document validation.
    """

    def compile(
        self,
        document_id: str,
        transaction: SemanticTransaction,
    ) -> CompiledSemanticTransaction:
        strict_result = super().compile(document_id, transaction)
        if strict_result.assessment.valid and strict_result.transaction is not None:
            return strict_result
        if any(issue.code == "revision_conflict" for issue in strict_result.assessment.issues):
            return strict_result

        current = self.service.get_document(document_id)
        accepted: list[SemanticOperation] = []
        for operation in transaction.operations:
            candidate = transaction.model_copy(
                update={
                    "expected_revision": current.revision,
                    "operations": [*accepted, operation],
                },
                deep=True,
            )
            result = super().compile(document_id, candidate)
            if result.assessment.valid and result.transaction is not None:
                accepted.append(operation)

        if not accepted:
            return strict_result

        skipped = len(transaction.operations) - len(accepted)
        label = transaction.label or "Agent semantic transaction"
        if skipped:
            label = f"{label} · applied {len(accepted)}/{len(transaction.operations)} operations"
        recovered = transaction.model_copy(
            update={
                "expected_revision": current.revision,
                "operations": accepted,
                "label": label,
            },
            deep=True,
        )
        return super().compile(document_id, recovered)
