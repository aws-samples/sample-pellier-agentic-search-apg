#!/usr/bin/env python3
"""
DEPRECATED — DO NOT RUN. Use scripts/seed_boutique_catalog.py instead.

This script targets the legacy product_catalog schema (columns like
product_description, imgurl, isbestseller, category_id) which does not
exist in the current pellier.product_catalog defined by
scripts/migrations/001_schema.sql. Running it against the current schema
will fail with "column does not exist".

The authoritative seeder is scripts/seed_boutique_catalog.py — it
generates Cohere Embed v4 embeddings for the 40 curated boutique
products and INSERTs them into pellier.product_catalog with the
matching column names. bootstrap-labs.sh calls that one.

Kept here only as historical reference. Delete in a future cleanup.
"""

import os
import sys
import json
import time
import logging
import argparse
from typing import Optional
from datetime import datetime

# Hard-fail at import time so anyone who runs this by accident gets a
# clear pointer instead of a confusing SQL error 30 seconds in.
sys.stderr.write(
    "ERROR: scripts/generate-embeddings.py is deprecated.\n"
    "       Use scripts/seed_boutique_catalog.py instead.\n"
)
sys.exit(2)

import boto3  # noqa: E402  unreachable, kept for grep / future revival
import pandas as pd  # noqa: E402
import psycopg  # noqa: E402
from pandarallel import pandarallel  # noqa: E402
from tqdm import tqdm  # noqa: E402

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'embedding_generation_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Initialize Bedrock client
bedrock_runtime = boto3.client('bedrock-runtime', region_name=os.getenv('AWS_REGION', 'us-west-2'))


def generate_embedding(text: str) -> Optional[list]:
    """
    Generate embedding for a single text using Cohere Embed v4 via Bedrock.
    Uses input_type="search_document" since these are product descriptions being indexed.

    Args:
        text: Text to embed

    Returns:
        Embedding vector (1024 dimensions) or None if failed
    """
    try:
        payload = json.dumps({
            'texts': [text],
            'input_type': 'search_document',
            'embedding_types': ['float'],
            'output_dimension': 1024,
        })
        response = bedrock_runtime.invoke_model(
            body=payload,
            modelId='us.cohere.embed-v4:0',
            accept="*/*",
            contentType="application/json"
        )
        response_body = json.loads(response.get("body").read())
        return response_body["embeddings"]["float"][0]
    except Exception as e:
        logger.error(f"Error generating embedding: {str(e)}")
        return None


def load_products_from_database(conn_params: dict, limit: Optional[int] = None) -> pd.DataFrame:
    """
    Load products from database that need embeddings
    
    Args:
        conn_params: Database connection parameters
        limit: Optional limit on number of products
        
    Returns:
        DataFrame with products
    """
    logger.info("Loading products from database...")
    
    conn = psycopg.connect(**conn_params)
    
    query = """
        SELECT 
            "productId",
            product_description,
            imgurl,
            producturl,
            stars,
            reviews,
            price,
            category_id,
            isbestseller,
            boughtinlastmonth,
            category_name,
            quantity
        FROM pellier.product_catalog
        WHERE embedding IS NULL
        ORDER BY "productId"
    """
    
    if limit:
        query += f" LIMIT {limit}"
    
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    logger.info(f"Loaded {len(df)} products from database")
    return df


def store_products(df: pd.DataFrame, conn_params: dict, batch_size: int = 1000):
    """
    Store products in database with batch processing and statistics
    
    Args:
        df: DataFrame with products and embeddings
        conn_params: Database connection parameters
        batch_size: Number of rows per batch
    """
    start_time = time.time()
    
    conn = psycopg.connect(**conn_params, autocommit=True)
    
    print(f"\nStoring products in database... Total rows to process: {len(df)}")
    
    try:
        with conn.cursor() as cur:
            batches = []
            total_processed = 0
            
            # Process data in batches
            for i, (_, row) in enumerate(df.iterrows(), 1):
                batches.append((
                    row['productId'],
                    row['product_description'],
                    row['imgurl'],
                    row['producturl'],
                    row['stars'],
                    row['reviews'],
                    row['price'],
                    row['category_id'],
                    row['isbestseller'],
                    row['boughtinlastmonth'],
                    row['category_name'],
                    row['quantity'],
                    row['embedding']
                ))
                
                # When batch size is reached or at the end, process the batch
                if len(batches) == batch_size or i == len(df):
                    batch_start = time.time()
                    
                    cur.executemany("""
                    INSERT INTO pellier.product_catalog (
                        "productId", product_description, imgurl, producturl,
                        stars, reviews, price, category_id, isbestseller,
                        boughtinlastmonth, category_name, quantity, embedding
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT ("productId") DO UPDATE 
                    SET 
                        product_description = EXCLUDED.product_description,
                        imgurl = EXCLUDED.imgurl,
                        producturl = EXCLUDED.producturl,
                        stars = EXCLUDED.stars,
                        reviews = EXCLUDED.reviews,
                        price = EXCLUDED.price,
                        category_id = EXCLUDED.category_id,
                        isbestseller = EXCLUDED.isbestseller,
                        boughtinlastmonth = EXCLUDED.boughtinlastmonth,
                        category_name = EXCLUDED.category_name,
                        quantity = EXCLUDED.quantity,
                        embedding = EXCLUDED.embedding;
                    """, batches)
                    
                    total_processed += len(batches)
                    batch_time = time.time() - batch_start
                    elapsed_total = time.time() - start_time
                    
                    # Calculate progress and estimated time remaining
                    progress = (total_processed / len(df)) * 100
                    avg_time_per_batch = elapsed_total / (total_processed / batch_size)
                    remaining_batches = (len(df) - total_processed) / batch_size
                    eta = remaining_batches * avg_time_per_batch
                    
                    print(f"\rProgress: {progress:.1f}% | Processed: {total_processed}/{len(df)} rows | "
                          f"Batch time: {batch_time:.2f}s | ETA: {eta:.0f}s", end="")
                    
                    batches = []
            
            print("\n\nRunning VACUUM ANALYZE...")
            cur.execute("VACUUM ANALYZE pellier.product_catalog;")
            
            # Get final statistics
            cur.execute("SELECT COUNT(*) FROM pellier.product_catalog")
            final_count = cur.fetchone()[0]
            
            end_time = time.time()
            total_time = end_time - start_time
            
            print("\n📊 Data Loading Statistics:")
            print(f"✓ Total rows loaded: {final_count:,}")
            print(f"✓ Total loading time: {total_time:.2f} seconds")
            print(f"✓ Average time per row: {(total_time/len(df))*1000:.2f} ms")
            print(f"✓ Average time per batch: {(total_time/(len(df)/batch_size)):.2f} seconds")
            print("\n✅ Products stored successfully in database")
            
    except Exception as e:
        logger.error(f"❌ Error storing products: {str(e)}")
        raise
    finally:
        conn.close()


def main():
    """Main execution function"""
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Generate embeddings and store products in Aurora PostgreSQL'
    )
    parser.add_argument('--workers', type=int, default=10, 
                       help='Number of parallel workers for embedding generation')
    parser.add_argument('--batch-size', type=int, default=1000, 
                       help='Batch size for database inserts')
    parser.add_argument('--limit', type=int, default=None, 
                       help='Limit number of products to process (for testing)')
    parser.add_argument('--region', type=str, default='us-west-2', 
                       help='AWS region for Bedrock')
    parser.add_argument('--skip-generate', action='store_true',
                       help='Skip embedding generation (only store existing embeddings)')
    parser.add_argument('--skip-store', action='store_true',
                       help='Skip database storage (only generate embeddings)')
    
    args = parser.parse_args()
    
    # Database connection parameters
    conn_params = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', 5432)),
        'dbname': os.getenv('DB_NAME', 'postgres'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD', ''),
    }
    
    logger.info("="*80)
    logger.info("Starting Embedding Generation and Storage Process")
    logger.info(f"Configuration:")
    logger.info(f"  - Workers: {args.workers}")
    logger.info(f"  - Batch size: {args.batch_size}")
    logger.info(f"  - Limit: {args.limit or 'No limit'}")
    logger.info(f"  - Region: {args.region}")
    logger.info(f"  - Skip generate: {args.skip_generate}")
    logger.info(f"  - Skip store: {args.skip_store}")
    logger.info("="*80)
    
    start_time = time.time()
    
    try:
        # Option 1: Load from database
        if not args.skip_generate:
            df = load_products_from_database(conn_params, limit=args.limit)
            
            if len(df) == 0:
                logger.info("No products need embeddings. Exiting.")
                return 0
            
            # Generate embeddings
            logger.info(f"\nGenerating embeddings for {len(df)} product descriptions...")
            logger.info(f"Initializing pandarallel with {args.workers} workers...")
            
            # Initialize parallel processing
            pandarallel.initialize(progress_bar=True, nb_workers=args.workers)
            
            # Generate embeddings in parallel
            # Run time: ~ 3 mins for ~21K products with 10 workers
            df['embedding'] = df['product_description'].parallel_apply(generate_embedding)
            
            logger.info("\nCompleted embedding generation")
            
            # Check for failed embeddings
            failed_count = df['embedding'].isna().sum()
            if failed_count > 0:
                logger.warning(f"⚠️  {failed_count} embeddings failed to generate")
                # Filter out failed embeddings
                df = df[df['embedding'].notna()]
        
        # Option 2: Load from CSV/file (if needed)
        # df = pd.read_csv('products_with_embeddings.csv')
        
        # Store in database
        if not args.skip_store and len(df) > 0:
            # Run time: ~ 2 mins for ~21K products
            store_products(df, conn_params, batch_size=args.batch_size)
        
        # Final statistics
        elapsed_time = time.time() - start_time
        
        logger.info("\n" + "="*80)
        logger.info("Process Complete!")
        logger.info(f"Statistics:")
        logger.info(f"  - Total products processed: {len(df)}")
        if not args.skip_generate:
            successful = df['embedding'].notna().sum()
            logger.info(f"  - Successful embeddings: {successful}")
            logger.info(f"  - Failed embeddings: {len(df) - successful}")
        logger.info(f"  - Total time: {elapsed_time:.2f} seconds ({elapsed_time/60:.2f} minutes)")
        logger.info(f"  - Average time per product: {(elapsed_time/len(df)):.3f} seconds")
        logger.info("="*80)
        
        logger.info("\n✅ Setup and data loading finished!")
        
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}", exc_info=True)
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
