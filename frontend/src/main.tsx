import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider, createBrowserRouter } from 'react-router-dom'
import './index.css'
import './activities/library.css'
import './activities/grid.css'
import './theme.css'
import App from './App.tsx'

// A data router so pages can warn before leaving with unsaved changes (useBlocker).
const router = createBrowserRouter([{ path: '*', element: <App /> }])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
