// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { DocumentRegister } from './document-register';

afterEach(cleanup);

describe('DocumentRegister', () => {
  it('renders the familiar document columns without fabricating revision metadata', () => {
    render(<DocumentRegister documents={[{ id: 'att_doc1', name: 'Method statement.pdf', type: 'PDF', revision: null, uploadedBy: 'usr_kwame', updated: '8 Aug 2026', siteUpdateId: 'sup_1', linkedRecords: ['tsk_1'] }]} />);
    expect(screen.getByRole('columnheader', { name: 'Name' })).toBeVisible();
    expect(screen.getByRole('columnheader', { name: 'Revision' })).toBeVisible();
    expect(screen.getByRole('row', { name: /Method statement.pdf/ })).toContainElement(screen.getByText('Not recorded'));
    expect(screen.getByText('tsk_1')).toBeVisible();
  });
});
