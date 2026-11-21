import React from 'react'
import { Link, useLocation } from 'react-router-dom'

export interface NavLinkProps {
  to: string
  children: React.ReactNode
  className?: string
  icon?: React.ReactNode
  end?: boolean
  onClick?: () => void
}

export function NavLink({ to, children, className = '', icon, end = false, onClick }: NavLinkProps) {
  const location = useLocation()
  const isActive = end ? location.pathname === to : location.pathname === to || location.pathname.startsWith(`${to}/`)

  return (
    <Link
      to={to}
      onClick={onClick}
      aria-current={isActive ? 'page' : undefined}
      className={`nx-nav-link ${isActive ? 'is-active' : ''} ${className}`}
    >
      {icon}
      {children}
    </Link>
  )
}
