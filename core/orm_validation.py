"""Automatic ORM Pre-condition Validation & Database Constraint Synchronizer for tender-bidding."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import String, event

logger = logging.getLogger("tender-bidding.orm_validation")


def register_orm_validation_listeners(base_cls: type) -> None:
    """Registers automatic pre-condition validation listeners for all models deriving from base_cls."""

    @event.listens_for(base_cls, "attribute_instrument", propagate=True)
    def _configure_attribute_validator(cls: type, key: str, inst: Any) -> None:
        prop = getattr(inst, "property", None)
        if prop and hasattr(prop, "columns") and prop.columns:
            col = prop.columns[0]
            max_len = col.type.length if (isinstance(col.type, String) and col.type.length is not None) else None
            is_nullable = col.nullable
            is_pk = col.primary_key
            has_default = col.default is not None or col.server_default is not None
            attr_name = key

            @event.listens_for(inst, "set", retval=True)
            def validate_attribute(target: Any, value: Any, oldvalue: Any, initiator: Any) -> Any:
                target_cls_name = target.__class__.__name__

                # 1. Non-null Pre-condition Check
                if value is None and not is_nullable and not is_pk and not has_default:
                    err_msg = (
                        f"Validation Error in {target_cls_name}.{attr_name}: "
                        f"Field is non-nullable but was set to None."
                    )
                    logger.error(err_msg)
                    raise ValueError(err_msg)

                # 2. String Length Pre-condition Check
                if value is not None and isinstance(value, str) and max_len is not None:
                    if len(value) > max_len:
                        err_msg = (
                            f"Validation Error in {target_cls_name}.{attr_name}: "
                            f"String length ({len(value)}) exceeds maximum allowed column length ({max_len})."
                        )
                        logger.error(err_msg)
                        raise ValueError(err_msg)

                return value
