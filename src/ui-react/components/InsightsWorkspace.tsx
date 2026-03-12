import React from 'react';
import { BarChart3, BookOpen, Clock3, Users } from 'lucide-react';
import { useProjectStore } from '../store';
import { useI18n } from '../i18n';

export const InsightsWorkspace = () => {
  const { characters, scenes, timelineEvents, worldItems } = useProjectStore();
  const { t, locale } = useI18n();

  const stats = [
    { id: 'characters', label: t('insights.characters'), value: characters.length, icon: <Users size={18} /> },
    { id: 'scenes', label: t('insights.scenes'), value: scenes.length, icon: <BookOpen size={18} /> },
    { id: 'timeline', label: t('insights.timeline'), value: timelineEvents.length, icon: <Clock3 size={18} /> },
    { id: 'world', label: t('insights.world'), value: worldItems.length, icon: <BarChart3 size={18} /> },
  ];

  const coverageBody =
    locale === 'zh-CN'
      ? `${characters.length} 个人物、${timelineEvents.length} 个时间线事件和 ${scenes.length} 个场景已经通过共享项目模型建立连接。`
      : `${characters.length} characters, ${timelineEvents.length} timeline events, and ${scenes.length} scenes are currently connected through the shared project model.`;

  const densityBody =
    locale === 'zh-CN'
      ? `${worldItems.length} 个世界条目已经支持路由筛选、场景联动、图板引用和发布附录。`
      : `${worldItems.length} world entries currently support route filtering, scene linking, graph references, and publish appendices.`;

  return (
    <div className="h-full overflow-y-auto bg-bg p-10" data-testid="insights-workspace">
      <div className="mb-8">
        <div className="text-[10px] font-black uppercase tracking-[0.3em] text-brand-2">{t('insights.title')}</div>
        <h1 className="mt-3 text-4xl font-black text-text">{t('insights.project')}</h1>
      </div>

      <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4" data-testid="insights-cards">
        {stats.map((stat) => (
          <div key={stat.id} className="rounded-2xl border border-border bg-card p-6 shadow-1">
            <div className="flex items-center justify-between text-text-3">
              <span className="text-[10px] font-black uppercase tracking-[0.25em]">{stat.label}</span>
              {stat.icon}
            </div>
            <div className="mt-6 text-4xl font-black text-text">{stat.value}</div>
          </div>
        ))}
      </div>

      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        <div className="rounded-2xl border border-border bg-card p-6 shadow-1">
          <div className="text-[10px] font-black uppercase tracking-[0.25em] text-text-3">{t('insights.coverageTitle')}</div>
          <p className="mt-4 text-sm leading-relaxed text-text-2">{coverageBody}</p>
        </div>
        <div className="rounded-2xl border border-border bg-card p-6 shadow-1">
          <div className="text-[10px] font-black uppercase tracking-[0.25em] text-text-3">{t('insights.densityTitle')}</div>
          <p className="mt-4 text-sm leading-relaxed text-text-2">{densityBody}</p>
        </div>
      </div>
    </div>
  );
};
