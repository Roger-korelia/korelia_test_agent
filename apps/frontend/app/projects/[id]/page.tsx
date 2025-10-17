import PipelineViewer from "./PipelineViewer";

export default async function ProjectPage(props: { params: Promise<{ id: string }> }) {
  const params = await props.params;
  return <PipelineViewer id={params.id} />;
}


