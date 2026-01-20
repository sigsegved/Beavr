"""Integration tests for full backtesting workflow."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from beavr.backtest.engine import BacktestEngine
from beavr.data.alpaca import AlpacaDataFetcher
from beavr.models.config import DipBuyDCAParams, SimpleDCAParams
from beavr.strategies.dip_buy_dca import DipBuyDCAStrategy
from beavr.strategies.simple_dca import SimpleDCAStrategy


@pytest.mark.slow
class TestFullBacktest:
    """Integration tests for complete backtest workflow."""

    def test_simple_dca_backtest(
        self, alpaca_credentials: tuple[str, str]
    ) -> None:
        """Test running a Simple DCA backtest with real data."""
        api_key, api_secret = alpaca_credentials
        
        data_fetcher = AlpacaDataFetcher(
            api_key=api_key,
            api_secret=api_secret,
        )
        
        params = SimpleDCAParams(symbols=["SPY"])
        strategy = SimpleDCAStrategy(params=params)
        
        engine = BacktestEngine(
            data_fetcher=data_fetcher,
        )
        
        # Run backtest for 6 months
        result = engine.run(
            strategy=strategy,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
            initial_cash=Decimal("10000"),
        )
        
        # Verify results structure
        assert result.run_id
        assert result.config.strategy_name == "Simple DCA"
        assert result.config.symbols == ["SPY"]
        
        # Verify metrics calculated
        assert result.metrics.total_trades > 0
        assert result.metrics.buy_trades > 0
        assert result.metrics.total_invested > Decimal("0")
        
        # Verify we have holdings
        assert len(result.final_positions) > 0
        assert result.final_cash < Decimal("10000")  # Some cash spent
        
        # Verify daily values tracked
        assert len(result.daily_values) > 100  # ~6 months of trading days

    def test_dip_buy_dca_backtest(
        self, alpaca_credentials: tuple[str, str]
    ) -> None:
        """Test running a Dip Buy DCA backtest with real data."""
        api_key, api_secret = alpaca_credentials
        
        data_fetcher = AlpacaDataFetcher(
            api_key=api_key,
            api_secret=api_secret,
        )
        
        params = DipBuyDCAParams(symbols=["SPY"])
        strategy = DipBuyDCAStrategy(params=params)
        
        engine = BacktestEngine(
            data_fetcher=data_fetcher,
        )
        
        result = engine.run(
            strategy=strategy,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
            initial_cash=Decimal("10000"),
        )
        
        # Verify results
        assert result.run_id
        assert result.config.strategy_name == "Dip Buy DCA"
        assert result.metrics.total_trades >= 0  # Might be 0 if no dips

    def test_compare_strategies(
        self, alpaca_credentials: tuple[str, str]
    ) -> None:
        """Test comparing two strategies on the same data."""
        api_key, api_secret = alpaca_credentials
        
        data_fetcher = AlpacaDataFetcher(
            api_key=api_key,
            api_secret=api_secret,
        )
        
        engine = BacktestEngine(data_fetcher=data_fetcher)
        
        # Run both strategies
        simple_params = SimpleDCAParams(symbols=["SPY"])
        simple_dca = SimpleDCAStrategy(params=simple_params)
        
        dip_params = DipBuyDCAParams(symbols=["SPY"])
        dip_buy = DipBuyDCAStrategy(params=dip_params)
        
        simple_result = engine.run(
            strategy=simple_dca,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
            initial_cash=Decimal("10000"),
        )
        
        dip_result = engine.run(
            strategy=dip_buy,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
            initial_cash=Decimal("10000"),
        )
        
        # Both should complete
        assert simple_result.run_id != dip_result.run_id
        assert simple_result.config.strategy_name != dip_result.config.strategy_name

    def test_backtest_returns_reasonable_results(
        self, alpaca_credentials: tuple[str, str]
    ) -> None:
        """Test that backtest returns sensible financial metrics."""
        api_key, api_secret = alpaca_credentials
        
        data_fetcher = AlpacaDataFetcher(
            api_key=api_key,
            api_secret=api_secret,
        )
        
        params = SimpleDCAParams(symbols=["SPY"])
        strategy = SimpleDCAStrategy(params=params)
        engine = BacktestEngine(data_fetcher=data_fetcher)
        
        result = engine.run(
            strategy=strategy,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
            initial_cash=Decimal("10000"),
        )
        
        # Total return should be reasonable (not extreme)
        assert -0.5 < result.metrics.total_return < 1.0
        
        # CAGR should be defined and reasonable
        assert result.metrics.cagr is not None
        assert -1.0 < result.metrics.cagr < 2.0
        
        # Max drawdown should be negative or zero
        assert result.metrics.max_drawdown is not None
        assert result.metrics.max_drawdown <= 0.01  # Allow small positive due to rounding
        
        # Final value should be positive
        assert result.final_value > Decimal("0")
