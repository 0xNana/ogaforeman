'use client';

import { ChevronLeft, ChevronRight } from 'lucide-react';

export interface PaginationProps {
  currentPage: number;
  totalItems: number;
  pageSize: number;
  onPageChange: (page: number) => void;
}

export function Pagination({ currentPage, totalItems, pageSize, onPageChange }: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));

  if (totalItems <= pageSize && currentPage === 1) {
    return null; // hide pagination if everything fits on one page
  }

  return (
    <div className="dashboard-pagination">
      <button
        type="button"
        className="btn btn-quiet btn-small"
        disabled={currentPage <= 1}
        onClick={() => onPageChange(currentPage - 1)}
      >
        <ChevronLeft size={14} /> Previous
      </button>

      <span>Page {currentPage} of {totalPages}</span>

      <button
        type="button"
        className="btn btn-quiet btn-small"
        disabled={currentPage >= totalPages}
        onClick={() => onPageChange(currentPage + 1)}
      >
        Next <ChevronRight size={14} />
      </button>
    </div>
  );
}
