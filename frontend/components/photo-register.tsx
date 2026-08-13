'use client';

import { Camera, ImageOff, MapPin } from 'lucide-react';
import Image from 'next/image';
import { useEffect, useMemo, useState } from 'react';

import { PageHeader } from '@/components/page-header';
import { RecordDetails, RecordDrawer } from '@/components/record-drawer';
import type { ProjectPhoto } from '@/lib/api';

type NamedRecord = { id: string; title?: string; description?: string; date?: string };

export function PhotoRegister({ photos, tasks, issues, dailyLogs, loadUrl }: Readonly<{ photos: ProjectPhoto[]; tasks: NamedRecord[]; issues: NamedRecord[]; dailyLogs: NamedRecord[]; loadUrl: (id: string) => Promise<string> }>) {
  const [date, setDate] = useState('all'); const [location, setLocation] = useState('all');
  const [task, setTask] = useState('all'); const [uploader, setUploader] = useState('all');
  const [selected, setSelected] = useState<ProjectPhoto | null>(null);
  const dates = unique(photos.map((photo) => photo.dateIso.slice(0, 10)));
  const locations = unique(photos.map((photo) => photo.location || 'Not recorded'));
  const uploaders = unique(photos.map((photo) => photo.uploadedBy));
  const taskNames = useMemo(() => new Map(tasks.map((item) => [item.id, item.title || item.id])), [tasks]);
  const visible = photos.filter((photo) => (date === 'all' || photo.dateIso.startsWith(date)) && (location === 'all' || (photo.location || 'Not recorded') === location) && (task === 'all' || photo.taskIds.includes(task)) && (uploader === 'all' || photo.uploadedBy === uploader));
  return <div><PageHeader eyebrow="Site evidence" title="Photos" description="Visual site records traced to the updates and project work they support." />
    <div className="register-toolbar media-filters" aria-label="Photo filters"><Filter label="Filter photos by date" value={date} onChange={setDate} options={dates} /><Filter label="Filter photos by location" value={location} onChange={setLocation} options={locations} /><Filter label="Filter photos by task" value={task} onChange={setTask} options={tasks.filter((item) => photos.some((photo) => photo.taskIds.includes(item.id))).map((item) => item.id)} names={taskNames} /><Filter label="Filter photos by uploader" value={uploader} onChange={setUploader} options={uploaders} /></div>
    {visible.length ? <div className="photo-grid" aria-label="Project photos">{visible.map((photo) => <button type="button" className="photo-tile" aria-label={`Open ${photo.name}`} onClick={() => setSelected(photo)} key={photo.id}><PhotoThumbnail photo={photo} loadUrl={loadUrl} /><span className="photo-tile-copy"><strong>{photo.name}</strong><span><MapPin size={13} aria-hidden="true" /> {photo.location || 'Location not recorded'}</span><small>{photo.date} · {photo.uploadedBy}</small></span></button>)}</div> : <div className="empty-state"><span className="empty-state-icon"><ImageOff size={20} aria-hidden="true" /></span><h2>No matching photos.</h2><p>Change a filter or submit a site photo through OG.</p></div>}
    {selected ? <PhotoDetail photo={selected} tasks={tasks} issues={issues} dailyLogs={dailyLogs} loadUrl={loadUrl} onClose={() => setSelected(null)} /> : null}
  </div>;
}

function PhotoThumbnail({ photo, loadUrl }: Readonly<{ photo: ProjectPhoto; loadUrl: (id: string) => Promise<string> }>) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => { let active = true; loadUrl(photo.id).then((value) => { if (active) setUrl(value); }).catch(() => undefined); return () => { active = false; }; }, [loadUrl, photo.id]);
  return <span className="photo-tile-preview">{url ? <Image src={url} loader={directImageLoader} unoptimized width={480} height={320} alt="" /> : <Camera size={28} aria-hidden="true" />}</span>;
}

function PhotoDetail({ photo, tasks, issues, dailyLogs, loadUrl, onClose }: Readonly<{ photo: ProjectPhoto; tasks: NamedRecord[]; issues: NamedRecord[]; dailyLogs: NamedRecord[]; loadUrl: (id: string) => Promise<string>; onClose: () => void }>) {
  const [url, setUrl] = useState<string | null>(null); const [error, setError] = useState(false);
  useEffect(() => { let active = true; loadUrl(photo.id).then((value) => { if (active) setUrl(value); }).catch(() => { if (active) setError(true); }); return () => { active = false; }; }, [loadUrl, photo.id]);
  const names = (ids: string[], records: NamedRecord[]) => ids.map((id) => { const record = records.find((item) => item.id === id); return record?.title || record?.description || record?.date || id; }).join(', ') || 'None recorded';
  return <RecordDrawer eyebrow={`Photo · ${photo.id}`} title={photo.name} onClose={onClose}><div className="photo-detail-preview">{url ? <Image src={url} loader={directImageLoader} unoptimized width={960} height={640} alt={`${photo.name} site evidence`} /> : error ? <span role="alert"><ImageOff size={24} /> Preview unavailable</span> : <span aria-busy="true">Loading photo…</span>}</div><RecordDetails items={[{ label: 'Date and time', value: photo.date }, { label: 'Uploaded by', value: photo.uploadedBy }, { label: 'Location', value: photo.location || 'Not recorded' }, { label: 'Source site update', value: photo.siteUpdateId || 'None recorded' }, { label: 'Linked tasks', value: names(photo.taskIds, tasks) }, { label: 'Linked issues', value: names(photo.issueIds, issues) }, { label: 'Linked daily logs', value: names(photo.dailyLogIds, dailyLogs) }]} /></RecordDrawer>;
}

function Filter({ label, value, onChange, options, names }: Readonly<{ label: string; value: string; onChange: (value: string) => void; options: string[]; names?: Map<string, string> }>) { return <label><span>{label.replace('Filter photos by ', '')}</span><select aria-label={label} value={value} onChange={(event) => onChange(event.target.value)}><option value="all">All</option>{options.map((option) => <option value={option} key={option}>{names?.get(option) || option}</option>)}</select></label>; }
function unique(values: string[]) { return [...new Set(values)]; }
function directImageLoader({ src }: { src: string }) { return src; }
