'use client';

import { ArrowRight, CircleSlash2, ListTodo, Plus, UserRound } from 'lucide-react';
import Link from 'next/link';
import { useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { api, type Task } from '@/lib/api';
import { TaskCreateDialog } from '@/components/task-create-dialog';
import { Pagination } from '@/components/pagination';

type TaskFilter = 'ACTIVE' | 'UPCOMING' | 'BLOCKED' | 'DONE';

const filters: Array<{ label: string; value: TaskFilter }> = [
  { label: 'Active', value: 'ACTIVE' },
  { label: 'Upcoming', value: 'UPCOMING' },
  { label: 'Blocked', value: 'BLOCKED' },
  { label: 'Done', value: 'DONE' },
];

export function TaskBoard({ projectId, tasks, onRefresh }: Readonly<{ projectId: string; tasks: Task[]; onRefresh: () => Promise<void> }>) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const isSetup = searchParams?.get('setup') === '1';
  const [filter, setFilter] = useState<TaskFilter>('ACTIVE');
  const [showCreate, setShowCreate] = useState(false);
  const visibleTasks = useMemo(() => tasks.filter((task) => {
    if (filter === 'BLOCKED') return task.status === 'BLOCKED';
    if (filter === 'DONE') return task.status === 'COMPLETED';

    // For ACTIVE and UPCOMING, strictly exclude completed and blocked tasks
    if (task.status === 'COMPLETED' || task.status === 'BLOCKED') return false;

    const label = task.dueLabel.toLowerCase();
    const isFuture = label.includes('tomorrow') || label.includes('upcoming') || label.includes('later');

    if (filter === 'UPCOMING') {
      return task.status === 'PENDING' && isFuture;
    }

    // ACTIVE includes IN_PROGRESS, PENDING tasks that are due today/overdue (not future), or anything needing attention
    return task.status === 'IN_PROGRESS' || (task.status === 'PENDING' && !isFuture) || task.needsAttention === true;
  }), [filter, tasks]);

  const [page, setPage] = useState(1);
  const pageSize = 15;
  const paginatedTasks = useMemo(() => {
    return visibleTasks.slice((page - 1) * pageSize, page * pageSize);
  }, [visibleTasks, page, pageSize]);

  function handleFilterChange(newFilter: TaskFilter) {
    setFilter(newFilter);
    setPage(1);
  }

  return (
    <div>
      <div className="page-heading"><div><span className="eyebrow">Lightweight task control</span><h1>Tasks</h1><p>What is moving, what is next and what is stuck.</p></div><div className="page-heading-actions"><button className="btn btn-primary btn-small" type="button" onClick={() => setShowCreate(true)}><Plus size={15} /> Add task</button>{isSetup && tasks.length > 0 && <Link href={`/projects/${projectId}?setup=1`} className="btn btn-accent btn-small">Next step <ArrowRight size={15} /></Link>}</div></div>
      <div className="resource-toolbar"><div className="filter-tabs" role="tablist" aria-label="Task views">{filters.map((item) => <button className={`filter-tab${filter === item.value ? ' active' : ''}`} type="button" role="tab" aria-selected={filter === item.value} onClick={() => handleFilterChange(item.value)} key={item.value}>{item.label}</button>)}</div><span className="faint" style={{ fontSize: '0.78rem' }}>{visibleTasks.length} {visibleTasks.length === 1 ? 'task' : 'tasks'}</span></div>
      {visibleTasks.length > 0 ? (
        <>
          <div className="data-table-wrapper">
            <table className="data-table">
              <thead>
                <tr>
                  <th style={{ width: '120px' }}>Status</th>
                  <th>Task</th>
                  <th style={{ width: '160px' }}>Assignee</th>
                  <th style={{ width: '160px' }}>Timeline</th>
                  <th style={{ width: '100px' }}></th>
                </tr>
              </thead>
              <tbody>
                {paginatedTasks.map((task) => (
                  <tr key={task.id}>
                    <td>
                      <span className={`status-pill ${task.status.toLowerCase()}`}>{task.status.replace('_', ' ')}</span>
                    </td>
                    <td>
                      <div className="primary-cell" style={{ marginBottom: '4px' }}>{task.title}</div>
                      {(task.blocking || task.note) && (
                        <div className="secondary-cell" style={{ whiteSpace: 'normal', lineHeight: 1.4 }}>
                          {task.blocking && <div style={{ color: 'var(--accent)', marginBottom: '4px' }}><strong>Blocking:</strong> {task.blocking}</div>}
                          {task.note && <div><strong>OG note:</strong> {task.note}</div>}
                        </div>
                      )}
                    </td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.86rem', color: 'var(--ink-soft)' }}>
                        <UserRound size={13} /> <strong>{task.assignee}</strong>
                      </div>
                    </td>
                    <td className="secondary-cell">{task.dueLabel}</td>
                    <td className="action-cell">
                      <Link className="btn btn-quiet btn-small" href={`/projects/${projectId}/site?task=${task.id}`}>
                        {task.status === 'BLOCKED' ? 'Resolve' : 'Open'}
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination
            currentPage={page}
            totalItems={visibleTasks.length}
            pageSize={pageSize}
            onPageChange={setPage}
          />
        </>
      ) : <div className="empty-state"><span className="empty-state-icon">{filter === 'BLOCKED' ? <CircleSlash2 size={20} /> : <ListTodo size={20} />}</span><h2>{filter === 'BLOCKED' ? 'No blocked tasks.' : 'No tasks found.'}</h2><p>{filter === 'BLOCKED' ? 'Everything is moving smoothly.' : 'Create tasks to track progress.'}</p></div>}
      {showCreate ? (
        <TaskCreateDialog
          projectId={projectId}
          onClose={() => setShowCreate(false)}
          onRefresh={onRefresh}
          onSuccess={() => setFilter('ACTIVE')}
        />
      ) : null}
    </div>
  );
}
