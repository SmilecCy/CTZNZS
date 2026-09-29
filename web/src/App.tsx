// ============================================================
// 文件：App.tsx
// ============================================================

import { useEffect } from 'react'
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
} from 'react-router-dom'

import { useAuthStore } from './stores/auth'
import { useAdminAuthStore } from './stores/adminAuth'
import UserLayout from './layouts/UserLayout'
import AdminLayout from './layouts/AdminLayout'
import Login from './pages/Login'
import Practice from './pages/Practice'
import WrongBook from './pages/WrongBook'
import Stats from './pages/Stats'
import AdminLogin from './pages/admin/AdminLogin'
import Dashboard from './pages/admin/Dashboard'
import CourseManage from './pages/admin/CourseManage'
import MaterialUpload from './pages/admin/MaterialUpload'
import MaterialClassify from './pages/admin/MaterialClassify'
import ChapterManage from './pages/admin/ChapterManage'
import ChunkClassification from './pages/admin/ChunkClassification'
import QuestionBank from './pages/admin/QuestionBank'
import SelfTest from './pages/admin/SelfTest'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated)
  const user = useAuthStore((state) => state.user)

  if (!isAuthenticated) return <Navigate to="/login" replace />
  if (user?.role === 'admin') return <Navigate to="/login" replace />
  return <>{children}</>
}

function RequireAdmin({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAdminAuthStore((state) => state.isAuthenticated)
  if (!isAuthenticated) return <Navigate to="/admin/login" replace />
  return <>{children}</>
}

function HomeRedirect() {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated)
  if (isAuthenticated) return <Navigate to="/practice" replace />
  return <Navigate to="/login" replace />
}

export default function App() {
  const loadFromStorage = useAuthStore((state) => state.loadFromStorage)
  const loadAdminFromStorage = useAdminAuthStore((state) => state.loadFromStorage)

  useEffect(() => {
    loadFromStorage()
    loadAdminFromStorage()
  }, [loadFromStorage, loadAdminFromStorage])

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomeRedirect />} />
        <Route path="/login" element={<Login />} />

        <Route
          element={
            <RequireAuth>
              <UserLayout />
            </RequireAuth>
          }
        >
          <Route path="/practice" element={<Practice />} />
          <Route path="/wrong-book" element={<WrongBook />} />
          <Route path="/stats" element={<Stats />} />
        </Route>

        <Route path="/admin/login" element={<AdminLogin />} />

        <Route
          element={
            <RequireAdmin>
              <AdminLayout />
            </RequireAdmin>
          }
        >
          <Route path="/admin/dashboard" element={<Dashboard />} />
          <Route path="/admin/courses" element={<CourseManage />} />
          <Route path="/admin/chapters" element={<ChapterManage />} />
          <Route path="/admin/materials" element={<MaterialUpload />} />
          <Route path="/admin/classify" element={<MaterialClassify />} />
          <Route path="/admin/chunk-classify" element={<ChunkClassification />} />
          <Route path="/admin/question-bank" element={<QuestionBank />} />
          <Route path="/admin/selftest" element={<SelfTest />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}