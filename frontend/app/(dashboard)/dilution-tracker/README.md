# Dilution Tracker - Frontend

Professional dilution analysis interface with comprehensive data visualization.

## Pages

### `/dilution-tracker`
Landing page with search functionality and feature overview

### `/dilution-tracker/[ticker]`
Detailed analysis page with 5 tabs:
- **Overview**: Risk scores + Cash runway summary
- **Dilution**: Historical shares outstanding + Offering history
- **Holders**: Institutional holders (13F filings)
- **Filings**: SEC filings with classification
- **Financials**: Balance sheets, Income statements, Cash flows

## Components

### `HoldersTable`
Professional table for institutional holders with:
- Position sizes and ownership percentages
- Position changes with visual indicators
- Form types and filing dates
- Responsive design

### `FilingsTable`
SEC filings display with:
- Filing type badges
- Category classification
- Dilutive event flagging
- External links to SEC

### `CashRunwayChart`
Cash position visualization with:
- Current cash metrics
- Burn rate analysis
- 12-month projection chart
- Risk level indicators

### `DilutionHistoryChart`
Shares outstanding history with:
- Historical bar chart
- 1-year and 3-year dilution metrics
- Interactive tooltips
- Color-coded risk levels

### `FinancialsTable`
Financial statements display with:
- Quarterly/Annual toggle
- Multi-period comparison
- Organized by statement type
- Key ratios calculation

## Design Principles

- Clean, professional interface without emojis
- Consistent color coding for risk levels
- Responsive grid layouts
- Dark mode support
- Accessibility-friendly
- Performance optimized

## Color Scheme

### Risk Levels
- **Critical**: Red (80-100)
- **High**: Orange (60-79)
- **Medium**: Yellow (40-59)
- **Low**: Green (0-39)

### Categories
- **Financial**: Blue
- **Offering**: Purple
- **Ownership**: Green
- **Proxy**: Yellow
- **Disclosure**: Orange

## Integration

Data will be fetched from the dilution-tracker backend service:

```typescript
// API endpoints
GET /api/analysis/{ticker}           // Complete analysis
GET /api/analysis/{ticker}/summary   // Quick summary
GET /api/analysis/{ticker}/risk-scores
GET /api/analysis/trending
```

## TODO

- [ ] Implement API integration
- [ ] Add real-time data fetching
- [ ] Add loading states
- [ ] Add error boundaries
- [ ] Add export functionality
- [ ] Add comparison mode
- [ ] Add alerts/notifications

