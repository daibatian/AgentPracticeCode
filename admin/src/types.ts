/** 用户列表里的一行 */
export interface AdminUserRow {
  id: number;
  username: string;
  display_name: string;
  created_at: string | null;
  is_admin: boolean;
  /** 该用户的额度覆盖值；null = 用全局默认额度 */
  weekly_token_quota: number | null;
  /** 实际生效的额度；0 = 不限 */
  effective_quota: number;
  used_this_week: number;
  remaining: number | null;
  requests_this_week: number;
  threads: number;
  sessions: number;
}

export interface UserPage {
  total: number;
  page: number;
  size: number;
  items: AdminUserRow[];
}

export interface UserDetail extends AdminUserRow {
  last_active: string | null;
  week: { start: string; end: string; resets_at: string };
  preferences: {
    taste: string;
    spicy_level: string;
    diet_goal: string;
    avoid_ingredients: string;
    preferred_cuisines: string[];
    notes: string;
  };
}
