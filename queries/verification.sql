-- Lakeshore Retail — verify agent answers against the source
-- Run these on the LakeshoreRetailLH SQL analytics endpoint.
-- Reach it from the lakehouse's child item in the workspace list, or the mode
-- switcher at the top-right of the lakehouse explorer.

-- 1. Stock at risk in one freezer. Compare with what the agent reports.
SELECT COUNT(DISTINCT ProductId) AS Products,
       SUM(UnitsOnHand)          AS Units,
       CAST(SUM(ValueUSD) AS DECIMAL(12,2)) AS ValueUSD
FROM factinventory
WHERE FreezerId = 'F-PAR-02';

-- 2. The detail behind it
SELECT InventoryId, ProductId, UnitsOnHand, UnitCostUSD, ValueUSD
FROM factinventory
WHERE FreezerId = 'F-PAR-02'
ORDER BY ProductId;

-- 3. Stock by freezer, across the estate
SELECT FreezerId,
       COUNT(DISTINCT ProductId) AS Products,
       SUM(UnitsOnHand)          AS Units,
       CAST(SUM(ValueUSD) AS DECIMAL(12,2)) AS ValueUSD
FROM factinventory
GROUP BY FreezerId
ORDER BY ValueUSD DESC;

-- 4. Most valuable product by STOCK VALUE (what the inventory agent ranks by)
SELECT TOP 5 p.ProductName,
       SUM(i.UnitsOnHand) AS Units,
       CAST(SUM(i.ValueUSD) AS DECIMAL(12,2)) AS StockValueUSD
FROM factinventory i
JOIN dimproducts p ON p.ProductId = i.ProductId
GROUP BY p.ProductName
ORDER BY StockValueUSD DESC;

-- 5. Most valuable product by REVENUE (what the sales agent ranks by)
--    Deliberately a different answer to query 4 - that is the point of the demo.
SELECT TOP 5 p.ProductName,
       CAST(SUM(s.RevenueUSD) AS DECIMAL(12,2)) AS RevenueUSD
FROM factsales s
JOIN dimproducts p ON p.ProductId = s.ProductId
GROUP BY p.ProductName
ORDER BY RevenueUSD DESC;

-- 6. Duplicate-looking inventory rows in one freezer.
--    Two rows with identical units AND value confused agent aggregation during
--    testing - one was dropped from a list, one double-counted in a total.
SELECT FreezerId, UnitsOnHand, ValueUSD, COUNT(*) AS Rows
FROM factinventory
GROUP BY FreezerId, UnitsOnHand, ValueUSD
HAVING COUNT(*) > 1;
