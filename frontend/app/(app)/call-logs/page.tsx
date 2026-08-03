import { CampaignCallLogsPageClient } from "@/components/call-logs/campaign-call-logs-page-client";

type CallLogsPageProps = {
  searchParams: Promise<{ campaignId?: string }>;
};

export default async function CallLogsPage({
  searchParams,
}: CallLogsPageProps) {
  const params = await searchParams;

  return (
    <CampaignCallLogsPageClient initialCampaignId={params.campaignId ?? ""} />
  );
}
