import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout.jsx";
import WeatherExplorer from "./pages/WeatherExplorer.jsx";
import HistoryDashboard from "./pages/HistoryDashboard.jsx";
import ComparePage from "./pages/ComparePage.jsx";
import BestTimePage from "./pages/BestTimePage.jsx";
import ModelInsightsPage from "./pages/ModelInsightsPage.jsx";
import NotFoundPage from "./pages/NotFoundPage.jsx";

// One route per page in the brief. Layout wraps them with the navbar and footer.
export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<WeatherExplorer />} />
        <Route path="history" element={<HistoryDashboard />} />
        <Route path="compare" element={<ComparePage />} />
        <Route path="best-time" element={<BestTimePage />} />
        <Route path="model-insights" element={<ModelInsightsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
