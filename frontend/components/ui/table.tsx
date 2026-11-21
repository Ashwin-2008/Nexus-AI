import React from 'react'

export interface TableHeaderProps {
  children: React.ReactNode
}

export function TableHeader({ children }: TableHeaderProps) {
  return <thead>{children}</thead>
}

export function Table({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return <table className={`nx-table ${className}`}>{children}</table>
}

export function TableHead({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return <th className={className}>{children}</th>
}

export interface TableRowProps extends React.HTMLAttributes<HTMLTableRowElement> {
  children: React.ReactNode
  className?: string
}

export function TableRow({ children, className = '', ...props }: TableRowProps) {
  return (
    <tr className={className} {...props}>
      {children}
    </tr>
  )
}

export interface TableCellProps extends React.TdHTMLAttributes<HTMLTableCellElement> {
  children: React.ReactNode
  className?: string
}

export function TableCell({ children, className = '', ...props }: TableCellProps) {
  return (
    <td className={className} {...props}>
      {children}
    </td>
  )
}

export interface TableBodyProps {
  children: React.ReactNode
}

export function TableBody({ children }: TableBodyProps) {
  return <tbody>{children}</tbody>
}
