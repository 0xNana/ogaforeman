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
  dueLabel: string;
  blocking?: string;
  note?: string;
};

export type CreateTaskInput = {
  title: string;
  description?: string;
  priority?: 'low' | 'medium' | 'high' | 'critical';
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
  user: string;
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

export type ProjectSnapshot = {
  project: Project;
  tasks: Task[];
  materials: Material[];
  approvals: Approval[];
  activities: Activity[];
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
  status: 'queued' | 'running' | 'waiting_for_approval' | 'waiting_for_clarification' | 'completed' | 'failed' | 'dead_lettered';
  step: string | null;
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

const demoSnapshot: ProjectSnapshot = {
  project: {
    id: '1',
    name: 'Ridge House',
    location: 'East Legon, Accra',
    status: 'ACTIVE',
    timezone: 'Africa/Accra',
  },
  tasks: [
    {
      id: 'tsk_blockwork',
      title: 'First-floor blockwork',
      status: 'COMPLETED',
      assignee: 'Kwame',
      dueLabel: 'Done today',
      note: 'Marked complete from this morning\'s site update.',
    },
    {
      id: 'tsk_electrical',
      title: 'Electrical rough-in',
      status: 'BLOCKED',
      assignee: 'Kofi',
      dueLabel: 'Due today',
      blocking: 'Ceiling installation',
      note: 'Electrician was reported absent in today\'s update.',
    },
    {
      id: 'tsk_plastering',
      title: 'Ground-floor plastering',
      status: 'PENDING',
      assignee: 'Ama',
      dueLabel: 'Starts tomorrow',
      note: 'Waiting on cement delivery.',
    },
    {
      id: 'tsk_ceiling',
      title: 'Ceiling installation',
      status: 'PENDING',
      assignee: 'Yaw',
      dueLabel: 'Upcoming',
      note: 'Follows electrical rough-in.',
    },
  ],
  materials: [
    {
      id: 'mat_cement',
      name: 'Cement',
      quantity: 10,
      unit: 'bags',
      need: 100,
      forWork: 'Ground-floor plastering',
      status: 'LOW',
      note: 'Current stock may not cover tomorrow\'s planned work.',
    },
    {
      id: 'mat_sand',
      name: 'Sharp sand',
      quantity: 18,
      unit: 'loads',
      need: 12,
      forWork: 'Plastering',
      status: 'OK',
      note: 'Enough for the next planned pour.',
    },
    {
      id: 'mat_blocks',
      name: '6-inch blocks',
      quantity: 420,
      unit: 'pieces',
      need: 300,
      forWork: 'Boundary wall',
      status: 'OK',
      note: 'Stock is above the current requirement.',
    },
  ],
  approvals: [
    {
      id: 'apr_cement',
      type: 'Material request',
      title: 'Cement request',
      status: 'PENDING',
      quantity: '100 bags',
      neededBy: 'Tomorrow',
      reason: 'Current stock may not cover tomorrow\'s plastering work.',
      requestedBy: 'Oga',
      date: 'Today, 09:42',
      version: 0,
    },
    {
      id: 'apr_scaffold',
      type: 'Follow-up',
      title: 'Scaffolding clearance',
      status: 'APPROVED',
      quantity: 'Site follow-up',
      neededBy: 'Today',
      reason: 'Clear access for the electrical team.',
      requestedBy: 'Oga',
      date: 'Yesterday, 16:18',
      version: 1,
    },
  ],
  activities: [
    {
      id: 'act_cement',
      kind: 'material',
      title: 'Cement shortage detected',
      description: 'Oga compared reported stock with tomorrow\'s plastering work and prepared a material request.',
      date: '09:42',
      user: 'Oga',
      needsAction: true,
      actionLabel: 'Review request',
    },
    {
      id: 'act_blocker',
      kind: 'blocker',
      title: 'Electrical work is blocking the ceiling',
      description: 'The electrician did not attend today. The follow-up is staying visible until the work moves.',
      date: '09:39',
      user: 'Oga',
      needsAction: true,
      actionLabel: 'Review blocker',
    },
    {
      id: 'act_progress',
      kind: 'progress',
      title: 'First-floor blockwork completed',
      description: 'Updated from Kwame\'s morning site report.',
      date: '09:38',
      user: 'Kwame',
    },
    {
      id: 'act_report',
      kind: 'report',
      title: 'Daily report updated',
      description: 'Today\'s progress, blocker and material risk are now in one clean report.',
      date: '09:43',
      user: 'Oga',
    },
  ],
  report: {
    date: 'Saturday, 8 August',
    completed: ['First-floor blockwork'],
    inProgress: ['Electrical rough-in'],
    blocked: ['Electrical work — electrician absent'],
    materials: ['Cement stock running low'],
    tomorrow: ['Ground-floor plastering'],
    risks: ['Plastering may be delayed if cement is not delivered.'],
    photos: [
      'https://images.unsplash.com/photo-1504307651254-35680f356dfd?auto=format&fit=crop&w=900&q=85',
      'https://images.unsplash.com/photo-1541888946425-d81bb19240f5?auto=format&fit=crop&w=900&q=85',
      'https://images.unsplash.com/photo-1503387762-592deb58ef4e?auto=format&fit=crop&w=900&q=85',
    ],
  },
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

const isDemoMode = (): boolean => process.env.NEXT_PUBLIC_DEMO_MODE === 'true';

const cloneSnapshot = (projectId: string): ProjectSnapshot => {
  const snapshot = structuredClone(demoSnapshot);
  snapshot.project.id = projectId;
  return snapshot;
};

function apiBaseUrl(): string {
  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (!baseUrl) {
    throw new ApiConfigurationError(
      'NEXT_PUBLIC_API_BASE_URL is required unless NEXT_PUBLIC_DEMO_MODE=true.',
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
    throw new ApiRequestError('Oga could not reach the project service.', {
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
  getApprovals: async (projectId: string): Promise<Approval[]> => (await api.getProjectSnapshot(projectId)).approvals,
  getActivities: async (projectId: string): Promise<Activity[]> => (await api.getProjectSnapshot(projectId)).activities,
  getReport: async (projectId: string): Promise<DailyReport> => (await api.getProjectSnapshot(projectId)).report,
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
      throw new ApiRequestError('Tell Oga what happened first.', {
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

export const demoApi = {
  getProjectSnapshot(projectId = 'prj_demo'): ProjectSnapshot {
    if (!isDemoMode()) {
      throw new ApiConfigurationError('Demo fixtures require NEXT_PUBLIC_DEMO_MODE=true.');
    }
    return cloneSnapshot(projectId);
  },
};
