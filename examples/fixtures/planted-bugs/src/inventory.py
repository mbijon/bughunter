"""Inventory tracking with transfers between warehouses."""

from typing import Dict


class InventoryStore:
    """In-memory inventory store."""

    def __init__(self) -> None:
        self._stock: Dict[str, Dict[str, int]] = {}

    def add(self, warehouse: str, sku: str, quantity: int) -> None:
        self._stock.setdefault(warehouse, {})
        self._stock[warehouse][sku] = self._stock[warehouse].get(sku, 0) + quantity

    def remove(self, warehouse: str, sku: str, quantity: int) -> None:
        if self._stock.get(warehouse, {}).get(sku, 0) < quantity:
            raise ValueError(f"insufficient stock of {sku} in {warehouse}")
        self._stock[warehouse][sku] -= quantity

    def get(self, warehouse: str, sku: str) -> int:
        return self._stock.get(warehouse, {}).get(sku, 0)


def transfer_items(
    store: InventoryStore,
    sku: str,
    quantity: int,
    source_warehouse: str,
    destination_warehouse: str,
) -> None:
    """Move ``quantity`` units of ``sku`` from source to destination."""

    # --- BUG F5: partial state mutation on failure (no rollback) ---
    # We remove from the source *first*, then attempt to add to the
    # destination. If the destination add raises (network error,
    # destination quota exceeded, destination doesn't exist, etc.) then
    # the source has already been permanently decremented. There is no
    # rollback, no try/except compensating write, and no transaction.
    # The inventory has silently leaked units.
    store.remove(source_warehouse, sku, quantity)

    # Imagine the destination write could fail for any number of reasons.
    store.add(destination_warehouse, sku, quantity)
