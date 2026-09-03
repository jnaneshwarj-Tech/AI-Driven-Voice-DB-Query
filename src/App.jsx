import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import Register from './pages/Register';
import Dashboard from './pages/Dashboard';
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/ResetPassword';

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/login"            element={<Login />} />
        <Route path="/register"         element={<Register />} />
        {/* OTP-based 3-step password reset flow (email → OTP → new password) */}
        <Route path="/forgot-password"  element={<ForgotPassword />} />
        {/* Fallback for direct navigation with reset_token (old link-based compat) */}
        <Route path="/reset-password/:token" element={<ResetPassword />} />
        <Route path="/reset-password"   element={<ResetPassword />} />
        <Route path="/dashboard"        element={<Dashboard />} />
        <Route path="/"                 element={<Navigate to="/login" replace />} />
        <Route path="*"                 element={<Navigate to="/login" replace />} />
      </Routes>
    </Router>
  );
}

export default App;
