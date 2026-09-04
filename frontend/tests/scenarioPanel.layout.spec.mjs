import { test, expect } from "@playwright/test";

async function openScenario(page) {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByRole("tab", { name: "Scenario", exact: true }).click();
  await expect(page.getByTestId("scenario-panel")).toBeVisible();
}

async function openAudit(page) {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByRole("tab", { name: "Audit", exact: true }).click();
  await expect(page.getByTestId("audit-log")).toBeVisible();
}

async function assertScenarioContainment(page) {
  const geometry = await page.evaluate(() => {
    const panel = document.querySelector('[data-testid="scenario-panel"]');
    const scroller = document.querySelector('[data-testid="scenario-scroll"]');
    const cyberSection = document.querySelector('[data-testid="scenario-cyber-section"]');
    const controls = [...document.querySelectorAll('[data-testid="scenario-cyber-section"] button')];
    if (!panel || !scroller || !cyberSection || controls.length !== 3) {
      throw new Error("Scenario layout test could not find the complete panel hierarchy");
    }

    const panelRect = panel.getBoundingClientRect();
    const scrollerRect = scroller.getBoundingClientRect();
    const beforeScroll = {
      panelBottom: panelRect.bottom,
      scrollerBottom: scrollerRect.bottom,
      cyberTop: cyberSection.getBoundingClientRect().top,
      cyberBottom: cyberSection.getBoundingClientRect().bottom,
    };

    const styles = {
      panelOverflow: getComputedStyle(panel).overflow,
      scrollerOverflowX: getComputedStyle(scroller).overflowX,
      scrollerOverflowY: getComputedStyle(scroller).overflowY,
      panelPosition: getComputedStyle(panel).position,
      panelZIndex: getComputedStyle(panel).zIndex,
    };

    scroller.scrollTop = scroller.scrollHeight;
    const afterScroll = {
      scrollTop: scroller.scrollTop,
      scrollHeight: scroller.scrollHeight,
      clientHeight: scroller.clientHeight,
      scrollerLeft: scrollerRect.left,
      scrollerRight: scrollerRect.right,
      cyberTop: cyberSection.getBoundingClientRect().top,
      cyberBottom: cyberSection.getBoundingClientRect().bottom,
      scrollerTop: scrollerRect.top,
      scrollerBottom: scrollerRect.bottom,
    };

    const controlBounds = controls.map((control) => {
      control.scrollIntoView({ block: "nearest", inline: "nearest" });
      const rect = control.getBoundingClientRect();
      return { top: rect.top, bottom: rect.bottom, left: rect.left, right: rect.right };
    });

    return { beforeScroll, afterScroll, controlBounds, styles };
  });

  expect(geometry.styles.panelOverflow).toBe("hidden");
  expect(geometry.styles.scrollerOverflowX).toBe("hidden");
  expect(geometry.styles.scrollerOverflowY).toBe("auto");
  expect(geometry.beforeScroll.scrollerBottom).toBeLessThanOrEqual(geometry.beforeScroll.panelBottom + 1);
  expect(geometry.afterScroll.scrollTop).toBeGreaterThanOrEqual(
    Math.max(0, geometry.afterScroll.scrollHeight - geometry.afterScroll.clientHeight - 1),
  );
  expect(geometry.afterScroll.cyberBottom).toBeLessThanOrEqual(geometry.afterScroll.scrollerBottom + 1);
  for (const control of geometry.controlBounds) {
    expect(control.left).toBeGreaterThanOrEqual(geometry.afterScroll.scrollerLeft - 1);
    expect(control.right).toBeLessThanOrEqual(geometry.afterScroll.scrollerRight + 1);
    expect(control.bottom).toBeLessThanOrEqual(geometry.afterScroll.scrollerBottom + 1);
  }
}

test("Scenario content stays contained and scrolls internally at desktop height", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 600 });
  await openScenario(page);
  await assertScenarioContainment(page);
  await expect(page.getByTestId("scenario-panel")).toHaveScreenshot("scenario-panel-desktop.png", { animations: "disabled" });
});

test("Scenario content stays contained at a narrow viewport", async ({ page }) => {
  await page.setViewportSize({ width: 647, height: 400 });
  await openScenario(page);
  await assertScenarioContainment(page);
  await expect(page.getByTestId("scenario-panel")).toHaveScreenshot("scenario-panel-narrow.png", { animations: "disabled" });
});

test("Audit toolbar wraps inside the right panel", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 800 });
  await openAudit(page);

  const geometry = await page.getByTestId("audit-log").evaluate((audit) => {
    const panel = audit.getBoundingClientRect();
    const toolbar = audit.querySelector(".scada-audit-toolbar").getBoundingClientRect();
    const actions = [...audit.querySelectorAll(".scada-audit-actions > *")].map((item) => {
      const rect = item.getBoundingClientRect();
      return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom };
    });
    return {
      panel: { left: panel.left, right: panel.right, bottom: panel.bottom },
      toolbar: { left: toolbar.left, right: toolbar.right, bottom: toolbar.bottom },
      actions,
      actionOverflow: getComputedStyle(audit.querySelector(".scada-audit-actions")).overflowX,
    };
  });

  expect(geometry.actionOverflow).toBe("visible");
  for (const action of geometry.actions) {
    expect(action.left).toBeGreaterThanOrEqual(geometry.toolbar.left - 1);
    expect(action.right).toBeLessThanOrEqual(geometry.toolbar.right + 1);
    expect(action.right).toBeLessThanOrEqual(geometry.panel.right + 1);
    expect(action.bottom).toBeLessThanOrEqual(geometry.panel.bottom + 1);
  }
  await expect(page.getByTestId("audit-log")).toHaveScreenshot("audit-panel-desktop.png", { animations: "disabled" });
});
