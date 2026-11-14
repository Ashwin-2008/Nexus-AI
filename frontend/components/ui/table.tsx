import React from 'react'

export interface TableHeaderProps {
  children: React.ReactNode
}

export function TableHeader({ children }: TableHeaderProps) {
  return (
    <thead>
      {children}
    </thead>
  )
}

export function Table({ children, className }: { children: React.ReactNode; className?: string }) {
  return <table className={className}>{children}</table>
}

export function TableHead({ children }: { children: React.ReactNode }) {
  return <th className="p-3 text-left">{children}</th>
}

export interface TableRowProps {
  children: React.ReactNode
  className?: string
}

export function TableRow({ children, className, ...props }: TableRowProps) {
  return (
    <tr className={className} {...props}>
      {children}
    </tr>
  )
}

export interface TableCellProps {
  children: React.ReactNode
  className?: string
}

export function TableCell({ children, className, ...props }: TableCellProps) {
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
  return (
    <tbody>{children}</tbody>
  )
}