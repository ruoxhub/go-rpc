// ParserWorkspace：页面局部 Zustand Provider 和一级工作区骨架。
"use client";

import { createContext, useContext, useState, type ReactNode } from "react";
import { useStore } from "zustand";
import { useShallow } from "zustand/react/shallow";

import { PageHeader } from "../../../../../../_components/PageHeader";
import { Button } from "../../../../../../_components/ui/button";
import { Card } from "../../../../../../_components/ui/card";
import { t } from "../../../../../../i18n";

import { StatusOverview } from "./components/StatusOverview";
import { SampleLibrary } from "./components/SampleLibrary";
import { SampleParamsForm } from "./components/SampleParamsForm";
import { SampleInspector } from "./components/SampleInspector";
import { DefinitionEditor } from "./components/DefinitionEditor";
import { DraftActions } from "./components/DraftActions";
import { AiSuggestion } from "./components/AiSuggestion";
import { PreviewPanel } from "./components/PreviewPanel";
import { RevisionHistory } from "./components/RevisionHistory";
import {
  createParserWorkspaceStore,
  type ParserWorkspaceSnapshot,
  type ParserWorkspaceStore,
} from "./store/parserWorkspaceStore";
import type { ParserWorkspaceState } from "./types";

const ParserWorkspaceContext = createContext<ParserWorkspaceStore | null>(null);

export function useParserWorkspace<T>(
  selector: (state: ParserWorkspaceSnapshot) => T,
) {
  const store = useContext(ParserWorkspaceContext);
  if (store === null) {
    throw new Error("ParserWorkspaceProvider is missing");
  }
  return useStore(store, selector);
}

function WorkspaceSection({ children }: { children: ReactNode }) {
  return (
    <section
      id="parser-workspace"
      role="tabpanel"
      aria-labelledby="parser-tab-workspace"
      className="grid gap-4"
    >
      <h2 className="text-lg font-semibold text-foreground">
        {t("parser.section.workspace")}
      </h2>
      <div className="hidden gap-4 lg:grid lg:grid-cols-2">{children}</div>
      <Card className="p-4 lg:hidden">
        <h3 className="font-medium text-foreground">
          {t("parser.workspace.readOnly")}
        </h3>
        <p className="mt-2 text-sm text-muted-foreground">
          {t("parser.workspace.readOnlyDescription")}
        </p>
      </Card>
    </section>
  );
}

function WorkspaceContent() {
  const {
    action,
    platformName,
    draft,
    published,
    samples,
    dirty,
    previewReport,
    activeSection,
    setActiveSection,
    activeSampleId,
  } = useParserWorkspace(
    useShallow((state) => ({
      action: state.action,
      platformName: state.platformName,
      draft: state.draft,
      published: state.published,
      samples: state.samples,
      dirty: state.dirty,
      previewReport: state.previewReport,
      activeSection: state.activeSection,
      setActiveSection: state.setActiveSection,
      activeSampleId: state.activeSampleId,
    })),
  );
  const enabled = action.ba_enabled
    ? t("common.enabled")
    : t("common.disabled");
  const tabs: Array<{
    id: ParserWorkspaceState["activeSection"];
    label: string;
  }> = [
    { id: "workspace", label: t("parser.section.workspace") },
    { id: "samples", label: t("parser.section.samples") },
    { id: "history", label: t("parser.section.history") },
  ];

  return (
    <main className="mx-auto grid w-full max-w-7xl gap-6 px-4 py-6 lg:px-8">
      <PageHeader
        title={t("parser.title", { action: action.ba_action })}
        description={t("parser.description", {
          platform: platformName,
          status: enabled,
        })}
      >
        <Button asChild variant="outline">
          <a href="/crawler/actions">
            {t("parser.back")}
          </a>
        </Button>
      </PageHeader>

      <StatusOverview
        published={published}
        draft={draft}
        dirty={dirty}
        previewReport={previewReport}
        sampleCount={samples.length}
      />
      <div
        role="tablist"
        aria-label={t("parser.sections")}
        className="flex gap-2 border-b border-border"
      >
        {tabs.map((tab) => (
          <button
            key={tab.id}
            id={`parser-tab-${tab.id}`}
            type="button"
            role="tab"
            aria-selected={activeSection === tab.id}
            aria-controls={`parser-${tab.id}`}
            onClick={() => setActiveSection(tab.id)}
            className="cursor-pointer border-b-2 border-transparent px-3 py-2 text-sm font-medium text-muted-foreground aria-selected:border-primary aria-selected:text-foreground"
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeSection === "workspace" ? (
        <WorkspaceSection>
          <div className="grid gap-6 lg:col-span-2">
            {/* 顶层：草稿与发布生命周期工具条 */}
            <DraftActions />

            {/* 步骤 1：响应样例获取与管理 */}
            <SampleParamsForm />

            {/* 步骤 2：数据提取规则制定工作台（左侧脱敏响应树，右侧字段定义编辑） */}
            <div className="grid gap-6 lg:grid-cols-2">
              <SampleInspector />
              <DefinitionEditor />
            </div>

            {/* AI 智能生成与辅助优化 */}
            <AiSuggestion />

            {/* 步骤 3：解析结果校验与数据预览 */}
            <PreviewPanel />
          </div>
        </WorkspaceSection>
      ) : null}
      {activeSection === "samples" ? (
        <SampleLibrary />
      ) : null}

      {activeSection === "history" ? (
        <RevisionHistory />
      ) : null}
    </main>
  );
}

export function ParserWorkspace({
  initialState,
}: {
  initialState: ParserWorkspaceState;
}) {
  const [store] = useState(() => createParserWorkspaceStore(initialState));

  return (
    <ParserWorkspaceContext.Provider value={store}>
      <WorkspaceContent />
    </ParserWorkspaceContext.Provider>
  );
}
