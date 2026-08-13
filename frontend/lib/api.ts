export type ProjectStatus = 'ACTIVE' | 'ON_HOLD' | 'COMPLETED';

export type Project = {
  id: string;
  name: string;
  location: string;
  status: ProjectStatus;
  timezone: string;
};

export type CreateProjectInput = {
  name: string;
  location: string;
  timezone: string;
};

export type BootstrapUser = {
  id: string;
  email: string;
  displayName: string;
};

export type TaskStatus = 'PENDING' | 'IN_PROGRESS' | 'COMPLETED' | 'BLOCKED';

export type Task = {
  id: string;
  title: string;
  status: TaskStatus;
  assignee: string;
  location?: string | null;
  trade?: string | null;
  startLabel?: string;
  startDate?: string | null;
  finishDate?: string | null;
  durationDays?: number | null;
  isMilestone?: boolean;
  downstreamIds?: string[];
  atRisk?: boolean;
  dueLabel: string;
  progress?: number;
  dependencyIds?: string[];
  blocking?: string;
  note?: string;
  needsAttention?: boolean;
  sourceRefs?: string[];
};

export type Issue = {
  id: string;
  description: string;
  type: 'BLOCKER' | 'DELAY_RISK' | 'SAFETY' | 'QUALITY' | 'OBSERVATION';
  severity: 'INFO' | 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  status: 'OPEN' | 'ACKNOWLEDGED' | 'MITIGATED' | 'RESOLVED' | 'DISMISSED';
  owner: string;
  dueLabel: string;
  taskIds: string[];
  evidenceRefs: string[];
  location?: string | null;
};

export type MaterialRequest = {
  id: string;
  materialId: string;
  materialName: string;
  quantity: number;
  unit: string;
  reason: string;
  neededBy: string;
  status: string;
  approvalId?: string | null;
};

export type CreateTaskInput = {
  title: string;
  description?: string;
  priority?: 'low' | 'medium' | 'high' | 'critical';
  planned_start?: string;
  planned_end?: string;
  is_milestone?: boolean;
};

export type MaterialStatus = 'OK' | 'LOW' | 'REQUESTED' | 'DELAYED';

export type Material = {
  id: string;
  name: string;
  quantity: number;
  unit: string;
  need: number;
  forWork: string;
  status: MaterialStatus;
  note: string;
  version: number;
};

export type CreateMaterialInput = {
  name: string;
  unit: string;
  available_quantity: number;
  minimum_required_quantity: number;
  upcoming_requirement_quantity?: number;
};

export type ApprovalStatus = 'PENDING' | 'APPROVED' | 'REJECTED';

export type Approval = {
  id: string;
  type: string;
  title: string;
  status: ApprovalStatus;
  quantity: string;
  neededBy: string;
  reason: string;
  requestedBy: string;
  date: string;
  version: number;
};

export type ActivityKind = 'progress' | 'blocker' | 'material' | 'report' | 'approval' | 'update';

export type Activity = {
  id: string;
  kind: ActivityKind;
  title: string;
  description: string;
  date: string;
  dateLabel: string;
  occurredAt: string;
  user: string;
  actorType: 'user' | 'agent' | 'system';
  action: string;
  entityType: string;
  entityId: string;
  needsAction?: boolean;
  actionLabel?: string;
};

export type DailyReport = {
  date: string;
  completed: string[];
  inProgress: string[];
  blocked: string[];
  materials: string[];
  tomorrow: string[];
  risks: string[];
  photos: string[];
};

export type DailyLog = {
  id: string;
  date: string;
  dateIso: string;
  summary: string;
  crew: string | null;
  weather: string | null;
  completed: string[];
  inProgress: string[];
  blocked: string[];
  materials: string[];
  deliveries: string[];
  inspections: string[];
  photos: string[];
  tomorrow: string[];
  risks: string[];
  sourceUpdateCount: number;
  status: string;
  version: number;
};

export type ProjectPhoto = {
  id: string;
  name: string;
  contentType: string;
  date: string;
  dateIso: string;
  uploadedBy: string;
  location: string | null;
  siteUpdateId: string | null;
  taskIds: string[];
  issueIds: string[];
  dailyLogIds: string[];
};

export type ProjectDocument = {
  id: string;
  name: string;
  type: string;
  revision: string | null;
  uploadedBy: string;
  updated: string;
  siteUpdateId: string | null;
  linkedRecords: string[];
};

export type ProjectSnapshot = {
  viewerId?: string | null;
  project: Project;
  tasks: Task[];
  issues: Issue[];
  materials: Material[];
  materialRequests: MaterialRequest[];
  approvals: Approval[];
  activities: Activity[];
  dailyLogs: DailyLog[];
  photos: ProjectPhoto[];
  documents: ProjectDocument[];
  report: DailyReport;
};

export type SiteUpdateResult = {
  site_update_id: string;
  event_id: string;
  agent_run_id: string;
  status: 'queued';
  status_url: string;
};

export type AgentRunState = {
  id: string;
  run_id: string;
  project_id: string;
  trigger_event_id: string;
  workflow: 'daily_site_update' | 'material_shortage' | 'blocker_delay' | 'daily_brief';
  status: 'queued' | 'running' | 'waiting_for_approval' | 'waiting_for_clarification' | 'completed' | 'failed' | 'dead_lettered';
  step: string | null;
  attempt: number;
  trace_id: string;
  started_at: string;
  updated_at: string;
  result_summary: string | null;
  pending_actions: string[];
  error_code: string | null;
  error_summary: string | null;
  completed_at: string | null;
};

export type SiteUpdateInput = {
  rawText?: string;
  transcript?: string;
  attachmentIds?: string[];
  inputType?: 'text' | 'voice' | 'photo' | 'mixed' | 'file';
};

type UploadGrant = {
  attachment_id: string;
  upload_url: string;
  required_headers: Record<string, string>;
};

export class ApiConfigurationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ApiConfigurationError';
  }
}

export class ApiRequestError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(message: string, options: { status: number; code: string }) {
    super(message);
    this.name = 'ApiRequestError';
    this.status = options.status;
    this.code = options.code;
  }
}

type ApiTokenProvider = (forceRefresh?: boolean) => Promise<string | null>;

let tokenProvider: ApiTokenProvider | null = null;

export function setApiTokenProvider(provider: ApiTokenProvider | null): void {
  tokenProvider = provider;
}

type ErrorEnvelope = {
  error?: {
    code?: string;
    message?: string;
  };
};

function apiBaseUrl(): string {
  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (!baseUrl) {
    throw new ApiConfigurationError(
      'NEXT_PUBLIC_API_BASE_URL is required.',
    );
  }
  return baseUrl.replace(/\/$/, '');
}

async function currentToken(forceRefresh = false): Promise<string | null> {
  if (tokenProvider) return tokenProvider(forceRefresh);
  const { getFirebaseIdToken } = await import('@/src/lib/firebase');
  return getFirebaseIdToken(forceRefresh);
}

async function remote<T>(path: string, init?: RequestInit): Promise<T> {
  const token = await currentToken();
  if (!token) {
    throw new ApiRequestError('Your session has expired. Sign in again.', {
      status: 401,
      code: 'AUTH_REQUIRED',
    });
  }

  let response: Response;
  try {
    response = await authenticatedFetch(path, token, init);
    if (response.status === 401) {
      const refreshedToken = await currentToken(true);
      if (refreshedToken) response = await authenticatedFetch(path, refreshedToken, init);
    }
  } catch (error) {
    if (error instanceof ApiConfigurationError) throw error;
    throw new ApiRequestError('OG could not reach the project service.', {
      status: 0,
      code: 'API_UNAVAILABLE',
    });
  }

  if (!response.ok) {
    let envelope: ErrorEnvelope = {};
    try {
      envelope = (await response.json()) as ErrorEnvelope;
    } catch {
      // Non-JSON proxy and platform errors are represented by the status below.
    }
    throw new ApiRequestError(
      envelope.error?.message ?? 'The project service could not complete that request.',
      {
        status: response.status,
        code: envelope.error?.code ?? `HTTP_${response.status}`,
      },
    );
  }

  return (await response.json()) as T;
}

function authenticatedFetch(path: string, token: string, init?: RequestInit): Promise<Response> {
  return fetch(`${apiBaseUrl()}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
      Authorization: `Bearer ${token}`,
    },
    cache: 'no-store',
  });
}

export const api = {
  bootstrapUser: async (displayName?: string): Promise<BootstrapUser> => remote<BootstrapUser>(
    '/api/v1/auth/bootstrap',
    {
      method: 'POST',
      body: JSON.stringify({ display_name: displayName?.trim() || null }),
    },
  ),
  listProjects: async (): Promise<Project[]> => {
    const response = await remote<{ data: Project[] }>('/api/v1/projects');
    return response.data;
  },
  createProject: async (input: CreateProjectInput): Promise<Project> => remote<Project>(
    '/api/v1/projects',
    {
      method: 'POST',
      body: JSON.stringify(input),
      headers: { 'Idempotency-Key': `project:${crypto.randomUUID()}` },
    },
  ),
  getProject: async (id: string): Promise<Project> => {
    return remote<Project>(`/api/v1/projects/${id}`);
  },
  getProjectSnapshot: async (id: string): Promise<ProjectSnapshot> => {
    return remote<ProjectSnapshot>(`/api/v1/projects/${id}/snapshot`);
  },
  getTasks: async (projectId: string): Promise<Task[]> => (await api.getProjectSnapshot(projectId)).tasks,
  createTask: async (projectId: string, input: CreateTaskInput): Promise<Task> => remote<Task>(
    `/api/v1/projects/${projectId}/tasks`,
    {
      method: 'POST',
      body: JSON.stringify(input),
      headers: { 'Idempotency-Key': `task:${crypto.randomUUID()}` },
    },
  ),
  getMaterials: async (projectId: string): Promise<Material[]> => (await api.getProjectSnapshot(projectId)).materials,
  createMaterial: async (projectId: string, input: CreateMaterialInput): Promise<Material> => remote<Material>(
    `/api/v1/projects/${projectId}/materials`,
    {
      method: 'POST',
      body: JSON.stringify(input),
      headers: { 'Idempotency-Key': `material:${crypto.randomUUID()}` },
    },
  ),
  adjustMaterialQuantity: async (
    projectId: string,
    materialId: string,
    quantityDelta: number,
    unit: string,
    expectedVersion: number,
    reason: string,
  ): Promise<Material> => remote<Material>(
    `/api/v1/projects/${projectId}/materials/${materialId}/adjust`,
    {
      method: 'POST',
      body: JSON.stringify({
        quantity_delta: quantityDelta,
        unit,
        expected_version: expectedVersion,
        reason,
      }),
      headers: { 'Idempotency-Key': `material-adjust:${crypto.randomUUID()}` },
    },
  ),
  getApprovals: async (projectId: string): Promise<Approval[]> => (await api.getProjectSnapshot(projectId)).approvals,
  getActivities: async (projectId: string): Promise<Activity[]> => (await api.getProjectSnapshot(projectId)).activities,
  getReport: async (projectId: string): Promise<DailyReport> => (await api.getProjectSnapshot(projectId)).report,
  editDailyLog: async (projectId: string, reportId: string, input: { summary: string; crew_summary?: string; weather_summary?: string; expected_version: number }): Promise<DailyLog> => remote<DailyLog>(
    `/api/v1/projects/${projectId}/daily-logs/${reportId}/edit`,
    {
      method: 'POST',
      body: JSON.stringify(input),
      headers: { 'Idempotency-Key': `daily-log-edit:${crypto.randomUUID()}` },
    },
  ),
  getAttachmentReadUrl: async (projectId: string, attachmentId: string): Promise<string> => {
    const result = await remote<{ read_url: string | null }>(`/api/v1/projects/${projectId}/uploads/${attachmentId}/read-url`);
    if (!result.read_url) throw new Error('The file is not available for viewing.');
    return result.read_url;
  },
  uploadSiteMedia: async (projectId: string, file: File): Promise<{ success: boolean; attachmentId?: string; error?: string }> => {
    if (file.size > 10 * 1024 * 1024) return { success: false, error: 'That file is larger than 10 MB.' };
    if (!file.type.startsWith('image/') && !file.type.startsWith('audio/') && file.type !== 'application/pdf') {
      return { success: false, error: 'Use a photo, audio note or PDF.' };
    }
    const bytes = await file.arrayBuffer();
    const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)))
      .map((value) => value.toString(16).padStart(2, '0'))
      .join('');
    const grant = await remote<UploadGrant>(`/api/v1/projects/${projectId}/uploads/sign`, {
      method: 'POST',
      body: JSON.stringify({
        content_type: file.type,
        original_name: file.name,
        byte_size: file.size,
        sha256: digest,
      }),
    });
    const uploadHeaders = Object.fromEntries(
      Object.entries(grant.required_headers).filter(([name]) => name.toLowerCase() !== 'content-length'),
    );
    const upload = await fetch(grant.upload_url, {
      method: 'PUT',
      body: file,
      headers: uploadHeaders,
    });
    if (!upload.ok) return { success: false, error: 'That attachment could not be uploaded.' };
    await remote(`/api/v1/projects/${projectId}/uploads/${grant.attachment_id}/verify`, {
      method: 'POST',
    });
    return { success: true, attachmentId: grant.attachment_id };
  },
  submitSiteUpdate: async (projectId: string, input: string | SiteUpdateInput): Promise<SiteUpdateResult> => {
    const payload: {
      raw_text?: string;
      transcript?: string;
      attachment_ids?: string[];
      input_type?: SiteUpdateInput['inputType'];
    } = typeof input === 'string'
      ? { raw_text: input.trim() }
      : {
          raw_text: input.rawText?.trim() || undefined,
          transcript: input.transcript?.trim() || undefined,
          attachment_ids: input.attachmentIds ?? [],
          input_type: input.inputType,
        };
    if (!payload.raw_text && !payload.transcript && !payload.attachment_ids?.length) {
      throw new ApiRequestError('Tell OG what happened first.', {
        status: 400,
        code: 'VALIDATION_FAILED',
      });
    }
    return remote<SiteUpdateResult>(`/api/v1/projects/${projectId}/site-updates`, {
      method: 'POST',
      body: JSON.stringify(payload),
      headers: { 'Idempotency-Key': `site-update:${crypto.randomUUID()}` },
    });
  },
  getAgentRun: async (projectId: string, runId: string): Promise<AgentRunState> => {
    return remote<AgentRunState>(`/api/v1/projects/${projectId}/agent-runs/${runId}`);
  },
  resolveApproval: async (
    projectId: string,
    approvalId: string,
    decision: 'APPROVE' | 'REJECT',
    expectedVersion: number,
  ): Promise<Approval> => {
    return remote<Approval>(`/api/v1/projects/${projectId}/approvals/${approvalId}/decision`, {
      method: 'POST',
      body: JSON.stringify({
        decision: decision === 'APPROVE' ? 'approved' : 'rejected',
        expected_version: expectedVersion,
      }),
      headers: { 'Idempotency-Key': `approval:${crypto.randomUUID()}` },
    });
  },
};
