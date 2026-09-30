getContent(){return this.getElContent().innerHTML;}
getElContent(){const el=this.editable.cloneNode(true);this.resources["clean_for_save_handlers"].forEach((cb)=>cb({root:el}));return el;}
