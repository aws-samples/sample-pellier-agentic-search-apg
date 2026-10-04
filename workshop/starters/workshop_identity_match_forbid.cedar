// Required Lab 4: complete the unless block, then add this policy with the
// AgentCore CLI. Gateway generates the target-qualified action id. The resource
// must name your deployed Gateway: the lab guide substitutes
// ${PELLIER_GATEWAY_ARN} from your environment before the policy is added.
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
  false
};
