const PDFDocument = require('pdfkit');
const fs = require('fs');
const path = require('path');
const unixPrint = require('unix-print');


const PORT = 3000;
const REFUND_RATE = 0.10; // 10 cents per container

const COLUMN_WIDTH_12_FONT = 36
const COLUMN_WIDTH_14_FONT = 31

unixPrint.getPrinters().then((printers) => {
    console.log(printers);
});

const divider = (length) => {
    return '-'.repeat(length);
};

const print_receipt = async (transactionNumber, totalCount, categories) => {
    try {
        const refundTotal = (totalCount * REFUND_RATE).toFixed(2);
        
        // Create a new PDF document
        const doc = new PDFDocument({
            size: [297.64, 380],
            margins: { left: 17, right: 17, top: 50, bottom: 20 }
        });
        const filePath = path.join(__dirname, 'temp-receipt.pdf');
        const writeStream = fs.createWriteStream(filePath);
        
        // Pipe PDF to writeStream
        doc.pipe(writeStream);
        
        // Add company logo (using a placeholder rectangle for this example)
        doc.image('recyclorobo-logo.png', (doc.page.width - 200) / 2, 20, { width: 200 })
        doc.moveDown()

        const idDividerWidth = COLUMN_WIDTH_14_FONT - 'Transaction ID'.length - transactionNumber.toString().length - 2

        // Add container categories
        doc.font('Roboto_Mono/static/RobotoMono-Bold.ttf').fontSize(14);
        doc.text(`Transaction ID ${divider(idDividerWidth)} ${transactionNumber}`).moveDown();
        doc.font('Roboto_Mono/RobotoMono-VariableFont_wght.ttf').fontSize(12);
        for (const [category, count] of Object.entries(categories)) {
            const dividerWidth = COLUMN_WIDTH_12_FONT - category.length - count.toString().length - 2
            doc.text(`${category} ${divider(dividerWidth)} ${count}`);
        }

        const totalDividerWidth = COLUMN_WIDTH_14_FONT - 'Total'.length - totalCount.toString().length - 2
        const totalRefundDividerWidth = COLUMN_WIDTH_14_FONT - 'Total Refund'.length - refundTotal.length - 3

        const time = new Date()
        const dateString = time.toLocaleDateString()
        const timeString = time.toLocaleTimeString()
        const dateDividerWidth = COLUMN_WIDTH_12_FONT - 'Date'.length - dateString.length - 2
        const timeDividerWidth = COLUMN_WIDTH_12_FONT - 'Time'.length - timeString.length - 2
        doc.moveDown()
            .font('Roboto_Mono/static/RobotoMono-Bold.ttf').fontSize(14)
            .text(`Total ${divider(totalDividerWidth)} ${totalCount}`)
            .text(`Total Refund ${divider(totalRefundDividerWidth)} $${refundTotal}`, { bold: true })
            .moveDown()
            .font('Roboto_Mono/RobotoMono-VariableFont_wght.ttf').fontSize(12)
            .text(`Date ${divider(dateDividerWidth)} ${dateString}`)
            .text(`Time ${divider(timeDividerWidth)} ${timeString}`)
            .moveDown()
            .text(`Thank you for recycling!`, { align: 'center' });
        

        doc.moveDown().image('recyclorobo-qrcode.png', (doc.page.width - 100) / 2, doc.y, { width: 100 })

        // Finalize PDF
        doc.end();
        
        // Wait for PDF to finish writing
        writeStream.on('finish', async () => {
            try {
                // Print the PDF
                await unixPrint.print(filePath, 'EPSON_TM-T20II');
                
                // Clean up temporary file
                fs.unlinkSync(filePath);
                
            } catch (printError) {
                console.log(printError)
            }
        });
        
    } catch (error) {
        console.log(error);
    }
};

print_receipt(123456, 120, {
    'can': 120,
    'plastic': 0
})