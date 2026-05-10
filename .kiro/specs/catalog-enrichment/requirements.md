# Requirements Document

## Introduction

The Pellier e-commerce demo application requires a comprehensive catalog overhaul to transition from a uniform, over-populated product catalog (1,008 products, 24 categories, 42 each, uniform quality) to a curated, query-backward-designed catalog (~446 products, variable per category, realistic distributions). The enrichment ensures every scripted demo query across 4 workshop modules returns 3–5 meaningful results, while introducing missing product categories (headphones, insulated drinkware, gift sets) and realistic quality/inventory distributions for teaching purposes.

## Glossary

- **Trim_Script**: The Python script (`scripts/trim-catalog.py`) that selects the best products to keep from the existing catalog based on scoring criteria
- **Add_Products_Script**: The Python script (`scripts/add-new-products.py`) that creates new product entries with Unsplash images and Cohere Embed v4 embeddings
- **Enrich_Script**: The Python script (`scripts/enrich-descriptions.py`) that modifies existing product descriptions with color, material, and clearance attributes and re-embeds them
- **Post_Load_SQL**: The SQL script (`scripts/post-load-adjustments.sql`) that redistributes star ratings and inventory quantities after CSV import
- **Load_Script**: The shell script (`scripts/load-database-fast.sh`) that loads the enriched CSV into Aurora PostgreSQL and runs post-load adjustments
- **Enriched_Catalog**: The definitive output CSV file (`data/product-catalog-enriched.csv`) containing all curated, added, and enriched products
- **Source_Catalog**: The existing CSV file (`data/product-catalog-cohere-v4.csv`) containing 1,008 products with Cohere Embed v4 embeddings
- **Locked_Product**: A product explicitly referenced in scripted demo queries, verification requirements, or the restock demo that the Trim_Script shall never remove (29 total)
- **Locked_Stock_Product**: A product whose inventory quantity is fixed to a specific value for demo purposes and the Post_Load_SQL shall not randomize (5 total: PSUNG0007, PSPRT0044, PMOBI0044, PMOBI0046, PKITC0043)
- **Demo_Critical_Category**: One of the 11 categories (Laptops, Smartphones, Mobile Accessories, Mens Shoes, Womens Shoes, Beauty, Skin Care, Kitchen Accessories, Sports Accessories, Mens Watches, Womens Watches) that retain 25 products each
- **Supporting_Category**: One of the 13 remaining categories (Fragrances, Furniture, Groceries, Home Decoration, Mens Shirts, Motorcycle, Sunglasses, Tablets, Tops, Vehicle, Womens Bags, Womens Dresses, Womens Jewellery) that retain 12 products each
- **Cohere_Embed_v4**: The Amazon Bedrock embedding model (`us.cohere.embed-v4:0`) producing 1024-dimensional vectors for semantic search
- **HNSW_Index**: The pgvector Hierarchical Navigable Small World index on the embedding column with parameters m=16, ef_construction=128
- **Unsplash_API**: The free-tier image search API limited to 50 calls per hour, used to source product images for new products
- **EARS_Pattern**: Easy Approach to Requirements Syntax, a structured pattern for writing unambiguous requirements

## Requirements

### Requirement 1: Catalog Trim — Remove Weakest Products

**User Story:** As a workshop facilitator, I want to reduce the catalog from 1,008 to 431 products by removing the weakest entries, so that the demo catalog is curated and each category has meaningful variety without noise.

#### Acceptance Criteria

1. WHEN the Trim_Script is executed against the Source_Catalog, THE Trim_Script SHALL produce a trimmed CSV containing exactly 431 products across all 24 existing categories.
2. THE Trim_Script SHALL retain 25 products for each of the 11 Demo_Critical_Categories: Laptops, Smartphones, Mobile Accessories, Mens Shoes, Womens Shoes, Beauty, Skin Care, Kitchen Accessories, Sports Accessories, Mens Watches, and Womens Watches.
3. THE Trim_Script SHALL retain 12 products for each of the 13 Supporting_Categories: Fragrances, Furniture, Groceries, Home Decoration, Mens Shirts, Motorcycle, Sunglasses, Tablets, Tops, Vehicle, Womens Bags, Womens Dresses, and Womens Jewellery.
4. THE Trim_Script SHALL preserve all 29 Locked_Products (PLAPT0001, PLAPT0016, PLAPT0007, PLAPT0026, PLAPT0033, PLAPT0010, PSMRT0001, PSMRT0009, PSMRT0039, PMOBI0002, PMOBI0004, PKITC0010, PKITC0005, PSPRT0022, PSPRT0027, PMSHO0011, PMSHO0016, PMSHO0017, PMSHO0018, PMSHO0021, PMSHO0036, PWSHO0019, PWSHO0009, PWSHO0022, PWSHO0028, PSUNG0007, PMWAT0001, PWBAG0001, PWBAG0002) regardless of their scoring rank.
5. WHEN selecting unlocked products to keep, THE Trim_Script SHALL score each product using a weighted formula: 40% review count (normalized), 30% description length (normalized to 200 characters), 20% isBestSeller flag, and 10% price diversity within category.
6. THE Trim_Script SHALL read from `data/product-catalog-cohere-v4.csv` and write to `data/product-catalog-trimmed.csv` preserving all original CSV columns including the embedding column.

### Requirement 2: Add New Products — Headphones and Audio

**User Story:** As a workshop attendee, I want the catalog to contain wireless headphones and noise-canceling audio products in Mobile Accessories, so that queries like "wireless headphones under $50" and "noise canceling headphones" return relevant results.

#### Acceptance Criteria

1. THE Add_Products_Script SHALL create exactly 6 new headphone/audio products in the Mobile Accessories category with productIds PMOBI0043 through PMOBI0048.
2. THE Add_Products_Script SHALL assign the following product descriptions, prices, star ratings, review counts, and quantities as specified: Sony WH-1000XM5 ($348.00, 4.8★, 5421 reviews, qty 312), Apple AirPods Pro 2nd Gen USB-C ($249.00, 4.7★, 8932 reviews, qty 8), JBL Tune 510BT ($29.95, 4.4★, 3241 reviews, qty 445), Samsung Galaxy Buds3 Pro ($229.99, 4.6★, 2876 reviews, qty 6), Beats Solo 4 ($199.99, 4.5★, 4102 reviews, qty 203), and Anker Soundcore Life Q20+ ($49.99, 4.4★, 6543 reviews, qty 538).
3. WHEN creating each new headphone product, THE Add_Products_Script SHALL fetch one image from the Unsplash_API using the designated search query for that product and store the resulting image URL in the imgUrl field.
4. WHEN creating each new headphone product, THE Add_Products_Script SHALL generate a 1024-dimensional embedding vector using Cohere_Embed_v4 via Amazon Bedrock for the product description.

### Requirement 3: Add New Products — Insulated Drinkware

**User Story:** As a workshop attendee, I want the catalog to contain insulated tumblers and water bottles in Sports Accessories, so that queries like "something to keep my drinks cold" and "stainless steel tumbler" return relevant results.

#### Acceptance Criteria

1. THE Add_Products_Script SHALL create exactly 4 new insulated drinkware products in the Sports Accessories category with productIds PSPRT0043 through PSPRT0046.
2. THE Add_Products_Script SHALL assign the following product descriptions, prices, star ratings, review counts, and quantities as specified: YETI Rambler 26oz ($40.00, 4.8★, 7891 reviews, qty 267), Stanley Quencher H2.0 40oz ($35.00, 4.7★, 12453 reviews, qty 4), Owala FreeSip 24oz ($27.99, 4.6★, 9234 reviews, qty 389), and Corkcicle Classic Canteen 16oz ($32.95, 4.5★, 3456 reviews, qty 156).
3. WHEN creating each new drinkware product, THE Add_Products_Script SHALL fetch one image from the Unsplash_API using the designated search query for that product and store the resulting image URL in the imgUrl field.
4. WHEN creating each new drinkware product, THE Add_Products_Script SHALL generate a 1024-dimensional embedding vector using Cohere_Embed_v4 via Amazon Bedrock for the product description.

### Requirement 4: Add New Products — Gift Sets

**User Story:** As a workshop attendee, I want the catalog to contain gift sets across Beauty, Kitchen Accessories, and Skin Care, so that queries like "gift for someone who loves cooking" and "trending in beauty" return relevant results.

#### Acceptance Criteria

1. THE Add_Products_Script SHALL create exactly 3 new gift set products: PBEAU0043 in Beauty, PKITC0043 in Kitchen Accessories, and PSKCA0043 in Skin Care.
2. THE Add_Products_Script SHALL assign the following product descriptions, prices, star ratings, review counts, and quantities as specified: Burt's Bees Essential Holiday Gift Set ($14.99, 4.7★, 5621 reviews, qty 711), Lodge Cast Iron Starter Gift Set ($79.99, 4.8★, 4321 reviews, qty 0), and CeraVe Skincare Gift Set ($34.99, 4.6★, 3892 reviews, qty 423).
3. WHEN creating each new gift set product, THE Add_Products_Script SHALL fetch one image from the Unsplash_API using the designated search query for that product and store the resulting image URL in the imgUrl field.
4. WHEN creating each new gift set product, THE Add_Products_Script SHALL generate a 1024-dimensional embedding vector using Cohere_Embed_v4 via Amazon Bedrock for the product description.

### Requirement 5: Unsplash API Rate Limit Compliance

**User Story:** As a developer running the enrichment scripts, I want the scripts to stay within the Unsplash free-tier rate limit, so that image fetching completes without API errors.

#### Acceptance Criteria

1. THE Add_Products_Script SHALL make no more than 13 total calls to the Unsplash_API across all new product image fetches (6 headphones + 4 drinkware + 3 gift sets).
2. WHILE fetching images from the Unsplash_API, THE Add_Products_Script SHALL remain within the 50 calls per hour free-tier rate limit.
3. IF an Unsplash_API call fails or returns no results, THEN THE Add_Products_Script SHALL log a warning with the productId and search query, and assign a placeholder image URL so that the product record remains valid.

### Requirement 6: Embedding Generation Compliance

**User Story:** As a developer running the enrichment scripts, I want all embedding generation to use the same Cohere Embed v4 model and produce 1024-dimensional vectors, so that semantic search remains consistent across old and new products.

#### Acceptance Criteria

1. THE Add_Products_Script SHALL use the Cohere_Embed_v4 model (`us.cohere.embed-v4:0`) via Amazon Bedrock for all 13 new product embeddings.
2. THE Enrich_Script SHALL use the Cohere_Embed_v4 model (`us.cohere.embed-v4:0`) via Amazon Bedrock for all re-embeddings of modified product descriptions.
3. THE Add_Products_Script and Enrich_Script SHALL produce embedding vectors of exactly 1024 dimensions for every product processed.
4. THE Add_Products_Script and Enrich_Script combined SHALL generate no more than 88 total embedding API calls (13 new products + approximately 75 enriched descriptions).

### Requirement 7: Enrich Descriptions — Color and Material Attributes

**User Story:** As a workshop attendee, I want product descriptions to include color and material information, so that queries like "blue running shoes" and "leather bag under $200" return relevant results via semantic search.

#### Acceptance Criteria

1. THE Enrich_Script SHALL append color availability text (e.g., "Available in Black.") to the following specific productIds using the predefined COLOR_MAP: Mens Shoes (PMSHO0011 in Black, PMSHO0016 in Navy Blue, PMSHO0017 in Grey, PMSHO0018 in White, PMSHO0021 in Orange, PMSHO0024 in All Black, PMSHO0031 in Core Black, PMSHO0036 in Charcoal), Womens Shoes (PWSHO0010 in Grey, PWSHO0019 in Navy, PWSHO0022 in Black, PWSHO0028 in Blue, PWSHO0032 in Lavender, PWSHO0039 in All White), Womens Bags (PWBAG0001 in Black Leather, PWBAG0002 in Brown Leather, PWBAG0004 in Signature Canvas, PWBAG0006 in Tan Suede, PWBAG0010 in Navy Nylon), Mens Shirts (PMSHR0001 in White, PMSHR0003 in Light Blue, PMSHR0005 in Navy Stripe, PMSHR0008 in Charcoal), Sunglasses (PSUNG0001 in Matte Black, PSUNG0003 in Tortoise, PSUNG0007 in Black, PSUNG0010 in Gold), Womens Dresses (PWDRS0001 in Black, PWDRS0003 in Floral Print, PWDRS0005 in Navy, PWDRS0008 in Burgundy), and Tops (PTOPS0001 in White, PTOPS0003 in Grey Heather, PTOPS0005 in Black, PTOPS0008 in Olive). IF a productId from the COLOR_MAP was removed during the trim step, THE Enrich_Script SHALL skip that entry and log a warning.
2. THE Enrich_Script SHALL append material descriptions to the following specific productIds using the predefined MATERIAL_MAP: Womens Bags (PWBAG0008 "crafted from premium full-grain leather", PWBAG0012 "made with recycled nylon fabric"), Furniture (PFURN0001 "solid walnut wood frame", PFURN0005 "Italian leather upholstery"), and Kitchen Accessories (PKITC0015 "forged from Japanese VG-10 stainless steel"). IF a productId from the MATERIAL_MAP was removed during the trim step, THE Enrich_Script SHALL skip that entry and log a warning.
3. WHEN a product description is modified with color or material text, THE Enrich_Script SHALL regenerate the embedding vector for that product using Cohere_Embed_v4.
4. THE Enrich_Script SHALL preserve the original product description content and append the new color or material text without removing existing information.

### Requirement 8: Enrich Descriptions — Clearance Products

**User Story:** As a workshop attendee, I want some products marked as clearance with reduced prices, so that queries like "best deals in laptops" return meaningful clearance results and the pricing agent has interesting data to analyze.

#### Acceptance Criteria

1. THE Enrich_Script SHALL prefix approximately 15 well-stocked product descriptions with "CLEARANCE — " text.
2. WHEN a product is marked as clearance, THE Enrich_Script SHALL reduce the product price by 60% from the original price.
3. WHEN a product description is modified with the clearance prefix, THE Enrich_Script SHALL regenerate the embedding vector for that product using Cohere_Embed_v4.
4. THE Enrich_Script SHALL select clearance products only from products with healthy stock levels (quantity greater than 100) to ensure clearance items are available for purchase.

### Requirement 9: Enriched Catalog Output

**User Story:** As a developer, I want a single definitive CSV file containing all trimmed, added, and enriched products, so that the database load process uses one consistent data source.

#### Acceptance Criteria

1. THE Enrich_Script SHALL produce the Enriched_Catalog file at `data/product-catalog-enriched.csv` containing approximately 444 products (431 trimmed + 13 new).
2. THE Enriched_Catalog SHALL contain all original CSV columns in the same order: productId, product_description, imgUrl, productURL, stars, reviews, price, category_id, isBestSeller, boughtInLastMonth, category_name, quantity, embedding.
3. THE Enriched_Catalog SHALL use the existing productId format (PXXXX0NNN pattern with a 2-to-4-letter category prefix followed by a zero-padded number) for all products.
4. THE Enriched_Catalog SHALL preserve all 24 existing category names exactly as they appear in the Source_Catalog without renaming or adding new categories.

### Requirement 10: Quality Distribution — Star Ratings

**User Story:** As a workshop facilitator, I want realistic star rating distribution across the catalog, so that the `WHERE stars >= 3.5` filter in vector search visibly excludes low-quality products and demonstrates the value of quality filtering.

#### Acceptance Criteria

1. THE Post_Load_SQL SHALL redistribute star ratings across the catalog to achieve the following distribution: 40% of products (approximately 180) at 4.5–5.0 stars, 35% (approximately 155) at 4.0–4.4 stars, 15% (approximately 65) at 3.5–3.9 stars, 7% (approximately 30) at 3.0–3.4 stars, and 3% (approximately 16) at 2.0–2.9 stars.
2. THE Post_Load_SQL SHALL preserve the star ratings of all Locked_Products at their original values specified in the Enriched_Catalog.
3. THE Post_Load_SQL SHALL ensure that approximately 46 products fall below the 3.5-star threshold to demonstrate the filtering value of the `WHERE stars >= 3.5` clause in the search query.

### Requirement 11: Inventory Distribution — Stock Levels

**User Story:** As a workshop facilitator, I want realistic inventory distribution across the catalog, so that `get_inventory_health()` returns a health score around 74%, `get_low_stock_products()` returns approximately 90 products, and the inventory agent demos are rich with actionable data.

#### Acceptance Criteria

1. THE Post_Load_SQL SHALL redistribute stock quantities across the catalog to achieve the following distribution: 6% of products (approximately 25) at 0 units (out of stock), 8% (approximately 35) at 1–5 units (critical), 12% (approximately 55) at 6–15 units (low), 34% (approximately 150) at 16–100 units (healthy), and 40% (approximately 181) at 100+ units (well-stocked).
2. THE Post_Load_SQL SHALL preserve the stock quantities of all Locked_Stock_Products at their specified values: PSUNG0007 at quantity 1, PSPRT0044 at quantity 4, PMOBI0044 at quantity 8, PMOBI0046 at quantity 6, and PKITC0043 at quantity 0. Note: PKITC0043 (Lodge Cast Iron Gift Set) is deliberately out-of-stock for inventory demo purposes.
3. THE Post_Load_SQL SHALL assign stock quantities only after the Enriched_Catalog has been loaded into the database, operating as a post-load adjustment.

### Requirement 12: Schema and Index Preservation

**User Story:** As a developer, I want the enrichment process to preserve the existing database schema, embedding model, index configuration, and productId format, so that the application code requires zero changes after the catalog overhaul.

#### Acceptance Criteria

1. THE Enriched_Catalog SHALL use the existing productId format: a 2-to-4-letter uppercase category prefix followed by a zero-padded 4-digit number (pattern PXXXX0NNN, e.g., PLAPT0001, PMOBI0043).
2. THE Load_Script SHALL create the product_catalog table with the same schema as the existing `scripts/seed-database.sh`: productId CHAR(10) PRIMARY KEY, product_description VARCHAR(500), imgUrl VARCHAR(200), productURL VARCHAR(40), stars NUMERIC(2,1), reviews INTEGER, price NUMERIC(8,2), category_id SMALLINT, isBestSeller BOOLEAN, boughtInLastMonth INTEGER, category_name VARCHAR(50), quantity SMALLINT, and embedding vector(1024).
3. THE Load_Script SHALL create the HNSW_Index on the embedding column with parameters m=16 and ef_construction=128 using vector_cosine_ops, matching the existing index configuration.
4. THE Load_Script SHALL preserve all existing secondary indexes: full-text search GIN index on product_description, category_name index, price partial index, stars partial index, composite category-price index, and bestseller partial index.

### Requirement 13: Load Script — Database Loading Pipeline

**User Story:** As a developer, I want a single shell script that loads the enriched catalog into Aurora PostgreSQL and applies post-load adjustments, so that the database can be fully rebuilt from scratch with one command.

#### Acceptance Criteria

1. THE Load_Script SHALL read the Enriched_Catalog from `data/product-catalog-enriched.csv` as the primary data source instead of the original Source_Catalog.
2. WHEN the Load_Script completes CSV import, THE Load_Script SHALL execute the Post_Load_SQL script to apply quality and inventory distribution adjustments.
3. THE Load_Script SHALL create the session management tables (conversations, messages, session_metadata, tool_uses) and their indexes, matching the existing `scripts/seed-database.sh` behavior.
4. THE Load_Script SHALL run VACUUM ANALYZE on the product_catalog table after all data loading and adjustments are complete.
5. IF the Enriched_Catalog file is not found at the expected path, THEN THE Load_Script SHALL fall back to the Source_Catalog at `data/product-catalog-cohere-v4.csv` and log a warning.

### Requirement 14: Verification — Module 1 Keyword vs Semantic Queries

**User Story:** As a workshop facilitator, I want all Module 1 scripted queries to return the expected results, so that the keyword-vs-semantic search demonstration works correctly during the workshop.

#### Acceptance Criteria

1. WHEN the query "MacBook Air" is executed as a keyword search against the Enriched_Catalog, THE database SHALL return at least 2 results including products PLAPT0001 and PLAPT0016.
2. WHEN the query "Samsung Galaxy S24" is executed as a keyword search against the Enriched_Catalog, THE database SHALL return at least 3 results including product PSMRT0001.
3. WHEN the query "something to keep my drinks cold" is executed as a semantic search against the Enriched_Catalog, THE database SHALL return at least 4 results including products from the insulated drinkware set (YETI, Stanley, Owala, Hydro Flask).
4. WHEN the query "gift for someone who loves cooking" is executed as a semantic search against the Enriched_Catalog, THE database SHALL return at least 4 results including the Lodge Cast Iron Gift Set (PKITC0043) and Victorinox Chef's Knife (PKITC0010).
5. WHEN the query "comfortable shoes for standing all day" is executed as a semantic search against the Enriched_Catalog, THE database SHALL return at least 4 results including Skechers Go Walk Joy (PWSHO0019) and Clarks Cloudsteppers (PWSHO0009).

### Requirement 15: Verification — Module 2 Agent Tool Queries

**User Story:** As a workshop facilitator, I want all Module 2 scripted queries to return the expected results through agent tools, so that the semantic search tool demonstrations work correctly during the workshop.

#### Acceptance Criteria

1. WHEN the `get_trending_products` tool is invoked, THE tool SHALL return products with high review counts including Stanley Tumbler (12,453 reviews), AirPods Pro (8,932 reviews), and YETI Rambler (7,891 reviews) among the top results.
2. WHEN the `search_products` tool is invoked with query "wireless headphones under $50" and max_price=50, THE tool SHALL return at least 2 results including JBL Tune 510BT ($29.95) and Anker Soundcore Life Q20+ ($49.99).
3. WHEN the `search_products` tool is invoked with query "stainless steel tumbler", THE tool SHALL return at least 4 results including YETI Rambler, Stanley Quencher, Owala FreeSip, and Corkcicle Canteen.
4. WHEN the `search_products` tool is invoked with query "noise canceling headphones", THE tool SHALL return at least 3 results including Sony WH-1000XM5, Apple AirPods Pro 2, and Anker Soundcore Life Q20+.
5. WHEN the `get_price_analysis` tool is invoked for the Laptops category, THE tool SHALL return a price range spanning from approximately $499 to $3,000.

### Requirement 16: Verification — Module 3 Multi-Agent Queries

**User Story:** As a workshop facilitator, I want all Module 3 scripted queries to return the expected results through the multi-agent system, so that the recommendation, pricing, and inventory agent demonstrations work correctly during the workshop.

#### Acceptance Criteria

1. WHEN the recommendation agent processes "find me running shoes under $80", THE agent SHALL return results including Skechers GOwalk (PMSHO0036, $74.99) among the matches.
2. WHEN the pricing agent processes "best deals in laptops", THE agent SHALL return clearance-tagged laptop products with reduced prices and category price statistics.
3. WHEN the inventory agent processes "what products need restocking", THE agent SHALL return approximately 90 low-stock products (quantity between 1 and 15).
4. WHEN the recommendation agent processes "blue running shoes", THE agent SHALL return results including Saucony Kinvara in Navy Blue (PMSHO0016) and Brooks Adrenaline in Blue (PWSHO0028) due to the enriched color descriptions.
5. WHEN the recommendation agent processes "leather bag under $200", THE agent SHALL return results including products with enriched leather material descriptions from Womens Bags (PWBAG0001 in Black Leather, PWBAG0002 in Brown Leather).
6. WHEN the recommendation agent processes "show me trending beauty products", THE agent SHALL return results including Burt's Bees Essential Holiday Gift Set (PBEAU0043, 5621 reviews) among the top beauty products.

### Requirement 17: Verification — Module 4 AgentCore Queries

**User Story:** As a workshop facilitator, I want all Module 4 scripted queries to work correctly with the Cedar authorization policy and session memory, so that the AgentCore demonstrations function as designed.

#### Acceptance Criteria

1. WHEN a restock request for product PSUNG0007 with 1000 units is submitted, THE Cedar authorization policy SHALL deny the request because the quantity exceeds the 500-unit maximum threshold.
2. WHEN a restock request for product PSUNG0007 with 200 units is submitted, THE Cedar authorization policy SHALL permit the request because the quantity is within the allowed threshold.
3. THE Enriched_Catalog SHALL contain product PSUNG0007 (Quay Sunglasses) with quantity 1 to serve as the restock demo target requiring urgent restocking.

### Requirement 18: File Manifest and Script Organization

**User Story:** As a developer, I want all enrichment scripts and output files organized in the existing project directory structure, so that the enrichment pipeline is discoverable and maintainable.

#### Acceptance Criteria

1. THE enrichment pipeline SHALL create the following new files: `scripts/trim-catalog.py`, `scripts/add-new-products.py`, `scripts/enrich-descriptions.py`, `scripts/post-load-adjustments.sql`, and `data/product-catalog-enriched.csv`.
2. THE enrichment pipeline SHALL modify the existing file `scripts/load-database-fast.sh` to reference the Enriched_Catalog and execute the Post_Load_SQL after data import.
3. THE Trim_Script, Add_Products_Script, and Enrich_Script SHALL execute sequentially as independent steps with explicit intermediate files: the Trim_Script SHALL read `data/product-catalog-cohere-v4.csv` and write `data/product-catalog-trimmed.csv`, the Add_Products_Script SHALL read `data/product-catalog-trimmed.csv` and write `data/product-catalog-trimmed-added.csv`, and the Enrich_Script SHALL read `data/product-catalog-trimmed-added.csv` and write the final `data/product-catalog-enriched.csv`.
4. THE Post_Load_SQL SHALL execute as part of the Load_Script after CSV import, not as a standalone step during the enrichment pipeline.
