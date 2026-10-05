// Lab 4, Task 4A: the credit limit. Provisioning deployed this file as the
// policy workshop_credit_limit, so as written it already blocks Nadia's
// approved credit. Complete the final unless block, check it with
//   python3 scripts/lab4_policy_check.py
// then update the deployed policy with
//   python3 scripts/provision_agentcore_end_to_end.py --repo-path "$PWD" --mode participant
// The deploy fills in ${PELLIER_GATEWAY_ARN} with your Gateway's ARN.
//
// Goal: staff may give at most $100 of store credit per approved review. The
// supplied baseline permit (give_store_credit_staff_scope) already limits the
// action to a token whose `custom:staff_scope` claim is `returns`, and no
// shopper permit names it; you do not re-author that. This forbid is the
// amount rule. Forbid wins over permit, so as written, `unless { false }`
// blocks every credit, staff included. The tool's `amount_cents` input is an
// integer in cents, and AgentCore Policy exposes it as `context.input`: let
// through only a valid amount up to and including $100 (10000 cents).
forbid(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"pellier-store-tools___give_store_credit",
  resource == AgentCore::Gateway::"${PELLIER_GATEWAY_ARN}"
)
unless {
  context.input has amount_cents &&
  context.input.amount_cents <= 10000
};
