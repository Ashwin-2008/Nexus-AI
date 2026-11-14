import React from 'react'

export interface CardProps {
  title?: string
  children: React.ReactNode
  className?: string
}

export function Card({ title, children, className, ...props }: CardProps) {
  return (
    <div className={`rounded-lg border border-border bg-card ${className}`} {...props}>
      {title && (
        <div className="flex items-start gap-3 pb-2">
          <div className="w-1 h-1/2 rounded-full bg-border flex-shrink-0"></div>
          <h3 className="text-sm font-medium truncate">{title}</h3>
        </div>
      )}
      <div className="p-6">{children}</div>
    </div>
  )
}