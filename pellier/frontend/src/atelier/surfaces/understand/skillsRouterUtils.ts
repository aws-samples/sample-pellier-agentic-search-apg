/**
 * Offline SkillRouter fallback when POST /skills/route is unreachable.
 */
import type { Skill } from '../../types';

export interface SkillRouteConsidered {
  name: string;
  reason: string;
}

export interface SkillRouteResult {
  loaded_skills: string[];
  considered: SkillRouteConsidered[];
  elapsed_ms: number;
  user_message: string;
}

export function routeSkillsOffline(query: string, skills: Skill[]): SkillRouteResult {
  const q = query.toLowerCase().trim();
  const tokens = q.split(/\s+/).filter((w) => w.length > 2);

  const scored = skills.map((skill) => {
    let score = 0;
    const matched: string[] = [];
    for (const signal of skill.signals) {
      const s = signal.toLowerCase();
      if (q.includes(s) || tokens.some((t) => s.includes(t) || t.includes(s))) {
        score += 1;
        matched.push(signal);
      }
    }
    if (q.includes(skill.persona)) score += 0.5;
    const reason =
      matched.length > 0
        ? `Signal overlap: ${matched.slice(0, 3).join(', ')}`
        : 'No persona signals matched this turn';
    return { skill, score, reason };
  });

  const ranked = [...scored].sort((a, b) => b.score - a.score);
  const loaded =
    ranked[0]?.score > 0 ? [ranked[0].skill.name] : [];

  return {
    loaded_skills: loaded,
    considered: ranked.map(({ skill, reason }) => ({
      name: skill.name,
      reason,
    })),
    elapsed_ms: 12,
    user_message: query,
  };
}

export function routerQueryForSkill(skill: Skill): string {
  const presets: Record<string, string> = {
    'the-packing-list': 'what would go with the Hadley shirt for Goa',
    'the-gift-table': 'wrap-ready gifts with no extra effort',
    'the-makers-shelf': 'hand-thrown ceramics for a slower morning',
  };
  return presets[skill.name] ?? skill.signals[0] ?? skill.description;
}
