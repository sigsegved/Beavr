"""Orchestrator engine for multi-agent coordination."""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from beavr.agents.base import AgentContext, AgentProposal
from beavr.models.signal import Signal
from beavr.orchestrator.blackboard import Blackboard

if TYPE_CHECKING:
    from beavr.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class OrchestratorEngine:
    """
    Coordinates multi-agent decision making.

    The orchestrator manages the daily decision cycle:
    1. Market analysis (sets regime)
    2. Trading agent proposals
    3. Risk gating / position limits
    4. Signal aggregation
    """

    def __init__(
        self,
        market_analyst: "BaseAgent",
        trading_agents: list["BaseAgent"],
        max_position_pct: float = 0.10,
        max_total_exposure: float = 0.95,
        min_cash_pct: float = 0.05,
    ) -> None:
        """
        Initialize orchestrator.

        Args:
            market_analyst: Market analyst agent (runs first)
            trading_agents: List of trading agents (run after analyst)
            max_position_pct: Maximum single position as % of portfolio
            max_total_exposure: Maximum total equity exposure
            min_cash_pct: Minimum cash to keep as buffer
        """
        self.market_analyst = market_analyst
        self.trading_agents = trading_agents
        self.max_position_pct = max_position_pct
        self.max_total_exposure = max_total_exposure
        self.min_cash_pct = min_cash_pct
        self.blackboard = Blackboard()

    def run_daily_cycle(self, ctx: AgentContext) -> list[Signal]:
        """
        Execute the full daily decision cycle.

        Args:
            ctx: Current market/portfolio context

        Returns:
            List of trading signals to execute
        """
        logger.info(f"=== Starting Daily Cycle for {ctx.current_date} ===")
        self.blackboard.clear()

        # Store initial context
        self.blackboard.set("context", ctx.model_dump(), source="orchestrator")
        self.blackboard.set("cycle_start", datetime.now().isoformat(), source="orchestrator")

        # Step 1: Market Analysis
        logger.info("Step 1: Running Market Analyst...")
        market_proposal = self.market_analyst.analyze(ctx)
        self.blackboard.set("market_analysis", market_proposal.model_dump(), source="market_analyst")

        # Extract regime and update context
        regime = market_proposal.extra.get("regime", "sideways")
        regime_confidence = market_proposal.extra.get("confidence", 0.5)
        risk_posture = market_proposal.extra.get("recommended_risk_posture", 0.5)

        # Update context with regime info
        ctx.regime = regime
        ctx.regime_confidence = regime_confidence
        ctx.risk_budget = self._calculate_risk_budget(risk_posture, ctx)

        logger.info(
            f"Market regime: {regime} (confidence: {regime_confidence:.2f}), "
            f"risk budget: {ctx.risk_budget:.1%}"
        )

        # Step 2: Run Trading Agents
        logger.info(f"Step 2: Running {len(self.trading_agents)} trading agents...")
        all_proposals: list[AgentProposal] = [market_proposal]

        for agent in self.trading_agents:
            logger.info(f"  Running {agent.name}...")
            try:
                proposal = agent.analyze(ctx)
                all_proposals.append(proposal)
                self.blackboard.set(
                    f"proposal_{agent.role}",
                    proposal.model_dump(),
                    source=agent.name,
                )
            except Exception as e:
                logger.error(f"  {agent.name} failed: {e}")

        # Step 3: Aggregate and Filter Signals
        logger.info("Step 3: Aggregating signals...")
        raw_signals = self._aggregate_signals(all_proposals)
        logger.info(f"  Raw signals: {len(raw_signals)}")

        # Step 4: Apply Risk Gates
        logger.info("Step 4: Applying risk gates...")
        gated_signals = self._apply_risk_gates(raw_signals, ctx)
        logger.info(f"  Gated signals: {len(gated_signals)}")

        # Step 5: Convert to Signal objects
        final_signals = self._create_signals(gated_signals, ctx)
        logger.info(f"  Final signals: {len(final_signals)}")

        # Store results
        self.blackboard.set("final_signals", [s.model_dump() for s in final_signals], source="orchestrator")
        self.blackboard.set("cycle_end", datetime.now().isoformat(), source="orchestrator")

        logger.info(f"=== Daily Cycle Complete: {len(final_signals)} signals ===")
        return final_signals

    def _calculate_risk_budget(self, risk_posture: float, ctx: AgentContext) -> float:
        """
        Calculate effective risk budget based on market conditions and drawdown.

        Args:
            risk_posture: Recommended risk from market analyst (0-1)
            ctx: Current context

        Returns:
            Effective risk budget (0-1)
        """
        base_budget = risk_posture

        # Reduce risk in drawdown (progressive de-risking)
        if ctx.current_drawdown >= 0.20:
            # At 20% drawdown, cut to 20% of base
            base_budget *= 0.20
        elif ctx.current_drawdown >= 0.15:
            # At 15% drawdown, cut to 40% of base
            base_budget *= 0.40
        elif ctx.current_drawdown >= 0.10:
            # At 10% drawdown, cut to 60% of base
            base_budget *= 0.60
        elif ctx.current_drawdown >= 0.05:
            # At 5% drawdown, cut to 80% of base
            base_budget *= 0.80

        return max(0.1, min(1.0, base_budget))

    def _aggregate_signals(
        self, proposals: list[AgentProposal]
    ) -> list[dict]:
        """
        Aggregate signals from all proposals.

        Args:
            proposals: List of agent proposals

        Returns:
            List of signal dictionaries
        """
        all_signals = []
        for proposal in proposals:
            for signal in proposal.signals:
                # Add source info
                signal["source_agent"] = proposal.agent_name
                signal["agent_conviction"] = proposal.conviction
                all_signals.append(signal)
        return all_signals

    def _apply_risk_gates(
        self, signals: list[dict], ctx: AgentContext
    ) -> list[dict]:
        """
        Apply risk management gates to signals.

        Args:
            signals: Raw signals from agents
            ctx: Current context

        Returns:
            Filtered/adjusted signals
        """
        gated = []
        max_position_value = ctx.portfolio_value * Decimal(str(self.max_position_pct))
        min_cash = ctx.portfolio_value * Decimal(str(self.min_cash_pct))
        available_cash = ctx.cash - min_cash

        for sig in signals:
            symbol = sig.get("symbol")
            action = sig.get("action")
            conviction = sig.get("conviction", 0.5)

            # Skip low conviction signals
            if conviction < 0.3:
                logger.debug(f"Skipping {symbol} {action}: low conviction ({conviction:.2f})")
                continue

            if action == "buy":
                amount = Decimal(str(sig.get("amount", 0)))

                # Cap at max position size
                if amount > max_position_value:
                    logger.debug(
                        f"Reducing {symbol} buy from ${amount:,.2f} to ${max_position_value:,.2f}"
                    )
                    amount = max_position_value
                    sig["amount"] = float(amount)

                # Cap at available cash
                if amount > available_cash:
                    if available_cash > Decimal("50"):
                        logger.debug(
                            f"Reducing {symbol} buy to available cash: ${available_cash:,.2f}"
                        )
                        amount = available_cash
                        sig["amount"] = float(amount)
                    else:
                        logger.debug(f"Skipping {symbol} buy: insufficient cash")
                        continue

                available_cash -= amount

            elif action == "sell":
                # Selling is generally allowed
                pass

            gated.append(sig)

        return gated

    def _create_signals(
        self, signal_dicts: list[dict], ctx: AgentContext
    ) -> list[Signal]:
        """
        Convert signal dictionaries to Signal objects.

        Args:
            signal_dicts: Filtered signal dictionaries
            ctx: Current context

        Returns:
            List of Signal objects
        """
        signals = []
        for sig_dict in signal_dicts:
            try:
                action = sig_dict.get("action", "hold")
                if action == "hold":
                    continue

                signal = Signal(
                    symbol=sig_dict["symbol"],
                    action=action,
                    amount=Decimal(str(sig_dict.get("amount"))) if sig_dict.get("amount") else None,
                    quantity=Decimal(str(sig_dict.get("quantity"))) if sig_dict.get("quantity") else None,
                    reason=sig_dict.get("reason", "AI agent recommendation"),
                    timestamp=datetime.now(),
                    confidence=sig_dict.get("conviction", 0.5),
                )
                signals.append(signal)
            except Exception as e:
                logger.error(f"Failed to create signal: {e}")

        return signals

    def get_cycle_summary(self) -> dict:
        """
        Get summary of the last cycle from blackboard.

        Returns:
            Dictionary with cycle summary
        """
        return self.blackboard.get_all()
