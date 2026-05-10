"""
Product models for Pellier
"""

from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class Product(BaseModel):
    """Base product model"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "productId": 1,
                "product_description": "Premium wireless headphones with active noise cancellation",
                "stars": 4.5,
                "price": 199.99,
            }
        }
    )

    productId: int = Field(..., description="Unique product identifier (1-92 in boutique catalog)")
    product_description: str = Field(..., description="Product description")
    imgurl: Optional[str] = Field(None, description="Product image URL")
    producturl: Optional[str] = Field(None, description="Product page URL")
    stars: Optional[float] = Field(None, ge=0, le=5, description="Product rating (0-5)")
    reviews: Optional[int] = Field(None, ge=0, description="Number of reviews")
    price: Optional[float] = Field(None, ge=0, description="Product price")
    category_name: Optional[str] = Field(None, description="Product category")


class ProductWithScore(Product):
    """Product with similarity score for search results"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "productId": 1,
                "product_description": "Premium wireless headphones",
                "stars": 4.5,
                "price": 199.99,
                "similarity_score": 0.89,
            }
        }
    )

    similarity_score: float = Field(
        ...,
        ge=0,
        le=1,
        description="Cosine similarity score (0-1)",
    )


class ProductSearchResult(ProductWithScore):
    """Alias for ProductWithScore for backward compatibility"""
    pass


class ProductFilters(BaseModel):
    """Filters for product search"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "min_price": 50.0,
                "max_price": 500.0,
                "min_stars": 4.0,
            }
        }
    )

    min_price: Optional[float] = Field(None, ge=0, description="Minimum price")
    max_price: Optional[float] = Field(None, ge=0, description="Maximum price")
    min_stars: Optional[float] = Field(None, ge=0, le=5, description="Minimum rating")


class InventoryStats(BaseModel):
    """Inventory statistics for Lab 2"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_products": 1000,
                "running_low_count": 42,
                "out_of_stock_count": 8,
                "avg_price": 149.99,
            }
        }
    )

    total_products: int = Field(..., description="Total number of products")
    running_low_count: int = Field(default=0, description="Number of low stock items")
    out_of_stock_count: int = Field(default=0, description="Number of out of stock items")
    avg_price: Optional[float] = Field(None, description="Average product price")
