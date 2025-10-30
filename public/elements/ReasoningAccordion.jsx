import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion"
import { Brain } from 'lucide-react'

export default function ReasoningAccordion() {
  return (
    <Accordion type="single" collapsible className="w-full mt-2 mb-2">
      <AccordionItem value="reasoning" className="border rounded-md">
        <AccordionTrigger className="px-4 py-2 hover:no-underline">
          <div className="flex items-center gap-2">
            <Brain className="h-4 w-4" />
            <span className="text-sm font-medium">View Reasoning Process</span>
          </div>
        </AccordionTrigger>
        <AccordionContent className="px-4 py-3 bg-muted/30">
          <div className="text-sm whitespace-pre-wrap font-mono">
            {props.reasoning}
          </div>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  )
}
