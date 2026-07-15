import { ContactsPageClient } from "@/components/contacts/contacts-page-client";

type ContactsPageProps = {
  searchParams: Promise<{ campaignId?: string }>;
};

export default async function ContactsPage({
  searchParams,
}: ContactsPageProps) {
  const params = await searchParams;

  return <ContactsPageClient initialCampaignId={params.campaignId ?? ""} />;
}
