---
inclusion: fileMatch
fileMatchPattern: "lab-content/**/*.md"
---

# Workshop Content Guidelines

## Lab Content Location

All lab content lives in `lab-content/builders/` (the 60-min Builder's Session).

## Writing Style

- Use Workshop Studio markdown syntax (:::alert, ::::expand, :::::tabs, :code blocks)
- Keep instructions concise — participants have limited time per module
- Always provide "Short on time?" copy-paste solutions at the top of each module
- Include verification steps after every challenge
- Use Mermaid diagrams for architecture visualization

## Agent References

When referencing agents or tools in content, use these exact names:

- Tools: `search_products`, `get_trending_products`, `get_price_analysis`, `get_product_by_category`, `get_inventory_health`, `get_low_stock_products`, `restock_product`, `compare_products`, `get_return_policy`
- Agents: `search_agent`, `product_recommendation_agent`, `price_optimization_agent`, `inventory_restock_agent`, `customer_support_agent`
- Display names: Search Agent, Recommendation Agent, Pricing Agent, Inventory Agent, Support Agent

## CFN Templates

- Assets folder: `pellier-vpc.yml`, `pellier-database.yml`, `pellier-code-editor.yml`
- Main stack: `static/genai-dat-406-labs.yml`
- Aurora Serverless v2 (0-16 ACU), not provisioned instances
