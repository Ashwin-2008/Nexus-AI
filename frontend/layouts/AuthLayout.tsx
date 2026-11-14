import React from 'react'
import { Outlet } from 'react-router-dom'

export default function AuthLayout() {
  return (
    <div className="min-h-screen bg-background p-4 md:p-8">
      <div className="max-w-md w-full space-y-8">
        <h2 className="text-3xl font-bold tracking-tight text-gray-900">
          NEXUS AI
        </h2>
        <p className="mt-4 text-lg text-gray-600">
          Enterprise Knowledge Intelligence Platform
        </p>

        <Outlet />
      </div>
    </div>
  )
}