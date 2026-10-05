// Lab 4, Task 4A solution: staff may give at most $100 of store credit per
// approved review. The forbid wins over any permit, so an over-limit credit is
// denied before the tool executes even though the staff permit
// (give_store_credit_staff_scope) matches it. The `unless` admits exactly a
// valid amount up to and including $100: `amount_cents` is an integer in cents
// on the tool's input schema, and AgentCore Policy exposes it as
// `context.input.amount_cents`. Shoppers stay denied by the baseline, which
// has no shopper permit for this action; this rule is not what denies them.
//
// Check it with python3 scripts/lab4_policy_check.py, then deploy it with
//   python3 scripts/provision_agentcore_end_to_end.py --repo-path "$PWD" --mode participant
forbid(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"pellier-store-tools___give_store_credit",
  resource == AgentCore::Gateway::"${PELLIER_GATEWAY_ARN}"
)
unless {
  context.input has amount_cents &&
  context.input.amount_cents <= 10000
};
