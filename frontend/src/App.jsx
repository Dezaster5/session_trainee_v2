import { Navigate, Route, Routes } from "react-router-dom";

import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";
import Dashboard from "./pages/Dashboard";
import ImportStatus from "./pages/ImportStatus";
import Leaderboard from "./pages/Leaderboard";
import LiveCodingResult from "./pages/LiveCodingResult";
import LiveCodingSession from "./pages/LiveCodingSession";
import LiveCodingSetup from "./pages/LiveCodingSetup";
import Login from "./pages/Login";
import Mistakes from "./pages/Mistakes";
import NotFound from "./pages/NotFound";
import Profile from "./pages/Profile";
import Register from "./pages/Register";
import SubjectDetail from "./pages/SubjectDetail";
import SubjectTopics from "./pages/SubjectTopics";
import Subjects from "./pages/Subjects";
import TestResult from "./pages/TestResult";
import TestSession from "./pages/TestSession";
import TestSetup from "./pages/TestSetup";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="/subjects" element={<Subjects />} />
          <Route path="/subjects/:id" element={<SubjectDetail />} />
          <Route path="/subjects/:id/topics" element={<SubjectTopics />} />
          <Route path="/subjects/:id/test" element={<TestSetup />} />
          <Route path="/subjects/:id/live-coding" element={<LiveCodingSetup />} />
          <Route path="/tests/:id" element={<TestSession />} />
          <Route path="/tests/:id/result" element={<TestResult />} />
          <Route path="/live-coding/:id" element={<LiveCodingSession />} />
          <Route path="/live-coding/:id/result" element={<LiveCodingResult />} />
          <Route path="/mistakes" element={<Mistakes />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/leaderboard" element={<Leaderboard />} />
          <Route path="/import" element={<ImportStatus />} />
        </Route>
      </Route>
      <Route path="/404" element={<NotFound />} />
      <Route path="*" element={<Navigate to="/404" replace />} />
    </Routes>
  );
}
