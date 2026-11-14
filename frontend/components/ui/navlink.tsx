import React from 'react'
import { useLocation } from 'react-router-dom'

export interface NavLinkProps {
  to: string
  children: React.ReactNode
  className?: string
}

export function NavLink({ to, children, className, ...props }: NavLinkProps) {
  const location = useLocation()
  const isActive = location.pathname === to

  return (
    <a
      href={to}
      className={`
        inline-flex items-center rounded-md px-3 py-2 text-sm font-medium 
        ${isActive ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-primary'}
        ${className}
      `}
      {...props}
    >
      {children}
    </a>
  )
}