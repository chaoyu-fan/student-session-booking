document.querySelectorAll('form.cancel-event').forEach(f=>f.addEventListener('submit',e=>{if(!confirm('确认取消该日程？如涉及学生，需另行通知学生。'))e.preventDefault()}));
