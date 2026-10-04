export interface Me {
  user_id: string;
  email: string;
  full_name: string;
  organization: string;
  roles: string[];
  permissions: string[];
  must_change_password: boolean;
}

export interface OrgInfo {
  slug: string;
  name: string;
  default_locale: string;
  branding: Record<string, unknown>;
}

export interface AuditLogItem {
  id: string;
  at: string;
  actor_user_id: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  after: Record<string, unknown> | null;
  request_id: string | null;
}

export interface AuditPage {
  items: AuditLogItem[];
  next_cursor: string | null;
}

export interface Problem {
  title?: string;
  detail?: string;
  status?: number;
  request_id?: string | null;
}
