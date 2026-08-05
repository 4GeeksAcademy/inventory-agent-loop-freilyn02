from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import csv
import os

app = FastAPI(title="Inventory Service")

CSV_FILE = "products.csv"
CSV_FIELDS = ["id", "name", "quantity", "unit"]
DEFAULT_THRESHOLD = 10


def ensure_csv_exists():
    """Create products.csv with headers if it doesn't exist yet."""
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, mode="w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()


ensure_csv_exists()


def read_all_products() -> list[dict]:
    """Read all products from products.csv and return them as a list of dicts."""
    ensure_csv_exists()
    with open(CSV_FILE, mode="r", newline="") as f:
        reader = csv.DictReader(f)
        products = []
        for row in reader:
            row["id"] = int(row["id"])
            row["quantity"] = int(row["quantity"])
            products.append(row)
        return products


def write_all_products(products: list[dict]):
    """Overwrite products.csv with the given list of products."""
    with open(CSV_FILE, mode="w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(products)


def get_next_id(products: list[dict]) -> int:
    """Return the next available product id (max existing id + 1, or 1 if empty)."""
    if not products:
        return 1
    return max(p["id"] for p in products) + 1


class ProductCreate(BaseModel):
    name: str = Field(..., min_length=1, description="Product name")
    quantity: int = Field(..., ge=0, description="Initial stock quantity")
    unit: str = Field(..., min_length=1, description="Unit of measurement, e.g. 'units', 'kg', 'bags'")


class StockUpdate(BaseModel):
    delta: int = Field(..., description="Signed quantity change. Positive to add stock, negative to remove stock")


@app.get("/inventory")
def get_inventory():
    """Return the current list of all products."""
    return read_all_products()


@app.post("/inventory", status_code=201)
def create_product(product: ProductCreate):
    """Create a new product and persist it to products.csv."""
    products = read_all_products()

    new_product = {
        "id": get_next_id(products),
        "name": product.name,
        "quantity": product.quantity,
        "unit": product.unit,
    }

    products.append(new_product)
    write_all_products(products)

    return new_product


@app.patch("/inventory/{product_id}")
def update_stock(product_id: int, update: StockUpdate):
    """Apply a signed quantity delta to an existing product."""
    products = read_all_products()

    target = next((p for p in products if p["id"] == product_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"Product with id {product_id} not found")

    new_quantity = target["quantity"] + update.delta
    if new_quantity < 0:
        raise HTTPException(status_code=400, detail=f"Cannot apply delta {update.delta}: would result in negative quantity ({new_quantity})")

    target["quantity"] = new_quantity
    write_all_products(products)

    return target


@app.get("/inventory/alerts")
def get_low_stock_alerts(threshold: int = DEFAULT_THRESHOLD):
    """Return products whose quantity is below the given threshold (default 10)."""
    products = read_all_products()
    return [p for p in products if p["quantity"] < threshold]