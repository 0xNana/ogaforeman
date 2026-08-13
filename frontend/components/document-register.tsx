'use client';

import { FileText } from 'lucide-react';

import { PageHeader } from '@/components/page-header';
import type { ProjectDocument } from '@/lib/api';

export function DocumentRegister({ documents }: Readonly<{ documents: ProjectDocument[] }>) {
  return <div><PageHeader eyebrow="Project files" title="Documents" description="A focused register of uploaded project documents and their record links." />
    {documents.length ? <div className="data-table-wrapper"><table className="data-table register-table document-register"><thead><tr><th>Name</th><th>Type</th><th>Revision</th><th>Uploaded by</th><th>Updated</th><th>Linked records</th></tr></thead><tbody>{documents.map((document) => { const records = [document.siteUpdateId, ...document.linkedRecords].filter((record): record is string => Boolean(record)); return <tr key={document.id}><th scope="row"><span className="document-name"><FileText size={16} aria-hidden="true" />{document.name}</span></th><td>{document.type}</td><td>{document.revision || 'Not recorded'}</td><td>{document.uploadedBy}</td><td>{document.updated}</td><td>{records.length ? records.map((record) => <span className="record-chip" key={record}>{record}</span>) : 'None recorded'}</td></tr>; })}</tbody></table></div> : <div className="empty-state"><span className="empty-state-icon"><FileText size={20} aria-hidden="true" /></span><h2>No documents available.</h2><p>PDFs submitted through OG will appear here with their persisted links.</p></div>}
  </div>;
}
