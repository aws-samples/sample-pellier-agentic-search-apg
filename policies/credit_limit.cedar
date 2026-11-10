// Lab 4, Task 4A: the credit limit. This forbid blocks give_store_credit
// unless the final unless block lets the call through; `unless { false }`
// lets nothing through. Read that block, apply the supplied rule with
//   uv run scripts/lab_run.py solution --lab 4 --task 4A
// check it with
//   uv run scripts/lab4_check.py --task 4A
// then update the deployed policy with
//   uv run scripts/provision_agentcore_end_to_end.py --repo-path "$PWD" --mode participant
// The deploy fills in ${PELLIER_GATEWAY_ARN} with your Gateway's ARN.
//
// Goal: staff may give at most $100 of store credit per approved review. The
// supplied baseline permit (give_store_credit_staff_scope) already limits the
// action to a token whose `custom:staff_scope` claim is `returns`, and no
// shopper permit names it; you do not re-author that. This forbid is the
// amount rule. Forbid wins over permit, so any credit the unless block does
// not let through is blocked, staff included. The tool's `amount_cents` input
// is an integer in cents, and AgentCore Policy exposes it as `context.input`:
// let through only a valid amount up to and including $100 (10000 cents).
forbid(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"pellier-store-tools___give_store_credit",
  resource == AgentCore::Gateway::"${PELLIER_GATEWAY_ARN}"
)
unless {
  false
};
