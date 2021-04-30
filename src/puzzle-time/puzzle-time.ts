import { html, render } from "lit-html";

import { streamService } from "../puzzle-pieces/stream.service";

import "./puzzle-time.css";

interface TemplateData
{
  time: number;
}

const tag = 'pm-puzzle-time'
//let lastInstanceId = 0;

customElements.define(tag,
  class PmPuzzleTime extends HTMLElement
  {
    static get _instanceID(): string
    {
      return '${tag} ${lastInstanceId++}'
    }
    private instanceId: string;
    private puzzleId: string;
    private time: number = 0;

    constructor()
    {
      super();
      this.instanceId = PmPuzzleTime._instanceID;
      const puzzleId = this.attributes.getNamedItem('puzzle-id');
      this.puzzleId = puzzleId ? puzzleId.value : "";
      //this.time = this.timer();

      streamService.subscribe(
      "puzzle/time",
      this.timer.bind(this),
      this.instanceId);

      streamService.connect(this.puzzleId);
      this.render();
    }

    template(data: TemplateData)
    {
      return html`
        <div class= "pm-PuzzleTime">
          <small class="pm-PuzzleTime-label">time:</small>
          <span class="pm-PuzzleTime-value">${data.time}</pan>
        </div>
      `;
    }

    get data(): TemplateData
    {
      return
      {
        time: this.time
      };
    }
    render()
    {
      render(this.template(this.data), this);
    }
    timer()
    {
      var startTime = new Date().getTime();
      this.time = Math.ceil((new Date().getTime() - startTime) / 1000);
    }
  }
);




