import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { climatePrediction, forecastPrediction } from "../test/fixtures.js";
import PredictionCard from "./PredictionCard.jsx";

describe("PredictionCard", () => {
  it("labels a climate estimate and shows U.S. units with ranges", () => {
    render(<PredictionCard prediction={climatePrediction} />);
    expect(screen.getByText("Climate estimate")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Zion National Park" })).toBeInTheDocument();
    expect(screen.getByText("67°F")).toBeInTheDocument(); // 19.6 °C high
    expect(screen.getByText("likely 57–78°F")).toBeInTheDocument();
    expect(screen.getByText(/about 1 day in 5/)).toBeInTheDocument();
    expect(screen.getByText("94")).toBeInTheDocument();
    expect(screen.getByText("Excellent")).toBeInTheDocument();
  });

  it("labels a forecast and shows its chance of rain and notes", () => {
    render(<PredictionCard prediction={forecastPrediction} />);
    expect(screen.getByText("Forecast")).toBeInTheDocument();
    expect(screen.getByText("4 days away")).toBeInTheDocument();
    expect(screen.getByText("40%")).toBeInTheDocument();
    expect(screen.getByText(/about 0.20 in expected/)).toBeInTheDocument();
    expect(screen.getByText("Snow is likely.")).toBeInTheDocument();
    expect(screen.getByText("Fair")).toBeInTheDocument();
  });

  it("explains the score with each component's weight", () => {
    render(<PredictionCard prediction={climatePrediction} />);
    expect(screen.getByText(/40% of score/)).toBeInTheDocument();
    expect(screen.getByText(/35% of score/)).toBeInTheDocument();
  });
});
