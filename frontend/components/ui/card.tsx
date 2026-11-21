import React from 'react'
import { cn } from '@/components/nx'

export interface CardProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'title'> {
  title?: React.ReactNode
  subtitle?: React.ReactNode
  actions?: React.ReactNode
  glow?: 'cyan' | 'violet' | false
  hover?: boolean
  flush?: boolean
}

export function Card({
  title,
  subtitle,
  actions,
  glow = false,
  hover = false,
  flush = false,
  children,
  className,
  ...props
}: CardProps) {
  return (
    <div
      className={cn(
        'nx-card',
        glow === 'cyan' && 'nx-card--glow',
        glow === 'violet' && 'nx-card--violet',
        hover && 'nx-card--hover',
        className,
      )}
      {...props}
    >
      {(title || actions) && (
        <div className="nx-card__head">
          <div>
            {title && <h3 className="nx-card__title">{title}</h3>}
            {subtitle && <p className="nx-card__sub">{subtitle}</p>}
          </div>
          {actions && <div className="nx-card__action">{actions}</div>}
        </div>
      )}
      <div className={cn('nx-card__body', flush && 'nx-card__body--flush')}>{children}</div>
    </div>
  )
}
